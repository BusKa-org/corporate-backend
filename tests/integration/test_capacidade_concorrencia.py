"""RF-14 sob concorrência — o lock de linha da viagem é o que impede overbooking.

Um teste sequencial não prova nada sobre esse lock: ele passaria mesmo se o
`with_for_update()` fosse removido. Aqui as duas declarações rodam de verdade
em conexões separadas, disputando o último assento.
"""

import threading
from datetime import UTC, datetime, timedelta

import pytest

from app.core.exceptions import ConflictError
from app.models.enum import StatusSolicitacao, StatusViagem
from app.models.viagem import AlunosConfirmados
from app.services.capacidade_service import validar_e_reservar
from tests.factories.user_factory import AlunoFactory


@pytest.fixture()
def rodada_com_um_assento(_db, viagem_ociosa, onibus):
    onibus.capacidade = 1
    viagem_ociosa.status = StatusViagem.BUFFER_ABERTO
    viagem_ociosa.buffer_expira_em = datetime.now(UTC) + timedelta(minutes=5)
    _db.session.commit()
    return viagem_ociosa


@pytest.fixture()
def dois_alunos(_db, organizacao):
    dupla = [AlunoFactory(organizacao_id=organizacao.id) for _ in range(2)]
    _db.session.add_all(dupla)
    _db.session.commit()
    return dupla


def test_duas_declaracoes_simultaneas_nao_estouram_a_capacidade(
    app, _db, rodada_com_um_assento, pontos_circuito, dois_alunos
):
    """Só um dos dois pode ficar com o único assento do trecho."""
    p1, p2, _, _ = pontos_circuito
    viagem_id = rodada_com_um_assento.id
    ids = [a.usuario_id for a in dois_alunos]

    # A barreira solta as duas threads no mesmo instante; sem isso uma
    # terminaria antes da outra começar e o teste viraria um caso sequencial.
    largada = threading.Barrier(2, timeout=10)
    resultados: dict[int, str] = {}

    def declarar(indice: int) -> None:
        # Cada thread abre o seu próprio contexto e, com ele, a sua própria
        # sessão e conexão — é o que torna a disputa real.
        with app.app_context():
            try:
                largada.wait()
                validar_e_reservar(viagem_id, ids[indice], p1.id, p2.id)
                resultados[indice] = "aceito"
            except ConflictError:
                resultados[indice] = "negado"
            except Exception as e:  # noqa: BLE001 — diagnóstico do teste
                resultados[indice] = f"erro: {type(e).__name__}: {e}"

    threads = [threading.Thread(target=declarar, args=(i,)) for i in range(2)]
    for t in threads:
        t.start()
    for t in threads:
        t.join(timeout=30)

    assert not any(t.is_alive() for t in threads), "deadlock: alguma thread não terminou"
    assert sorted(resultados.values()) == [
        "aceito",
        "negado",
    ], f"esperado exatamente um aceito e um negado, veio {resultados}"

    _db.session.expire_all()
    confirmados = (
        _db.session.query(AlunosConfirmados)
        .filter_by(viagem_id=viagem_id, status=StatusSolicitacao.CONFIRMADO)
        .count()
    )
    assert confirmados == 1, "capacidade estourada: o lock não serializou as declarações"
