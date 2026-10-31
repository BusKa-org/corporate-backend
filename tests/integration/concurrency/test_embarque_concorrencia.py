"""Embarque por QR sob concorrência (RF-17/RF-18): ninguém embarca duas vezes.

A confirmação dupla do mesmo QR já está em tests/integration/test_embarque.py.
Aqui ficam as disputas entre caminhos diferentes: QR contra manual, QR contra
recusa e a mesma fila offline enviada duas vezes ao mesmo tempo.
"""

from datetime import UTC, datetime, timedelta

import pytest

from app.models.credencial_embarque import CredencialEmbarque
from app.models.ocorrencia import Ocorrencia
from app.models.viagem import AlunosConfirmados, TelemetriaViagem
from tests.integration.concurrency.conftest import ao_mesmo_tempo, status_de
from tests.integration.test_embarque import _com_foto, _consolidar, _qr

pytestmark = [pytest.mark.integration, pytest.mark.concurrency]


@pytest.fixture()
def rodada(_db, viagem_buffer_aberto, pontos_circuito, aluno):
    """Viagem em andamento com o `aluno` embarcando em P1, com foto e credencial."""
    p1, p2, _, _ = pontos_circuito
    viagem = _consolidar(_db, viagem_buffer_aberto, [(aluno.user.id, p1, p2)])
    # Emitida há uma hora, para os eventos offline caberem depois da emissão.
    for credencial in _db.session.query(CredencialEmbarque).filter_by(viagem_id=viagem.id):
        credencial.created_at = datetime.now(UTC) - timedelta(hours=1)
    _db.session.commit()
    _com_foto(_db, aluno)
    return viagem


def _post(app, motorista, viagem, caminho, corpo):
    return lambda: app.test_client().post(
        f"/v1/embarque/viagens/{viagem.id}/{caminho}", json=corpo, headers=motorista.headers
    )


def _codigo_erro(resposta) -> str:
    return resposta.get_json()["error"]["code"]


def _registro(_db, viagem, aluno) -> AlunosConfirmados:
    _db.session.expire_all()
    return _db.session.get(AlunosConfirmados, (viagem.id, aluno.user.id))


def test_qr_e_manual_ao_mesmo_tempo_embarcam_uma_vez(app, _db, rodada, motorista, aluno):
    respostas = ao_mesmo_tempo(
        app,
        [
            _post(app, motorista, rodada, "confirmacao", {"qr_token": _qr(_db, rodada, aluno)}),
            _post(app, motorista, rodada, "manual", {"aluno_id": str(aluno.user.id)}),
        ],
    )

    assert status_de(respostas) == [200, 409]
    for resposta in respostas:
        if resposta.status_code == 409:
            assert _codigo_erro(resposta) == "CREDENCIAL_JA_UTILIZADA"
    assert _registro(_db, rodada, aluno).embarcou is True


def test_confirmar_e_recusar_o_mesmo_qr_ao_mesmo_tempo(app, _db, rodada, motorista, aluno):
    """Vence quem travar primeiro; o outro vê o estado gravado e é recusado."""
    qr = _qr(_db, rodada, aluno)
    confirmacao, recusa = ao_mesmo_tempo(
        app,
        [
            _post(app, motorista, rodada, "confirmacao", {"qr_token": qr}),
            _post(app, motorista, rodada, "recusa", {"qr_token": qr, "motivo": "FOTO_NAO_CONFERE"}),
        ],
    )

    assert status_de([confirmacao, recusa]) == [200, 409]
    embarcou = _registro(_db, rodada, aluno).embarcou
    if confirmacao.status_code == 200:
        assert embarcou is True
        assert _codigo_erro(recusa) == "CREDENCIAL_JA_UTILIZADA"
    else:
        assert embarcou is False
        assert _codigo_erro(confirmacao) == "CREDENCIAL_RECUSADA"


def test_mesma_fila_offline_enviada_duas_vezes_ao_mesmo_tempo(
    app, _db, rodada, motorista, aluno, pontos_circuito
):
    """O app reenvia a fila quando a rede oscila; cada evento vale uma vez só."""
    momento = datetime.now(UTC) - timedelta(minutes=5)
    eventos = [
        {
            "evento_id": "ev-recusa",
            "tipo": "RECUSA",
            "ocorrido_em": momento.isoformat(),
            "qr_token": _qr(_db, rodada, aluno, momento),
            "ponto_id": str(pontos_circuito[0].id),
            "motivo": "FOTO_NAO_CONFERE",
        },
        {
            "evento_id": "ev-posicao",
            "tipo": "POSICAO",
            "ocorrido_em": (momento + timedelta(minutes=1)).isoformat(),
            "latitude": "-7.21",
            "longitude": "-35.88",
        },
        {
            "evento_id": "ev-manual",
            "tipo": "EMBARQUE_MANUAL",
            "ocorrido_em": (momento + timedelta(minutes=2)).isoformat(),
            "aluno_id": str(aluno.user.id),
            "ponto_id": str(pontos_circuito[0].id),
        },
    ]
    corpo = {"eventos": eventos}

    respostas = ao_mesmo_tempo(
        app,
        [
            _post(app, motorista, rodada, "sincronizacao", corpo),
            _post(app, motorista, rodada, "sincronizacao", corpo),
        ],
    )

    assert status_de(respostas) == [200, 200]
    for resposta in respostas:
        lote = resposta.get_json()
        assert lote["recusados"] == 0, lote["resultados"]
        assert lote["aplicados"] + lote["ja_aplicados"] == 3
    _db.session.expire_all()
    # A recusa e o embarque manual geram uma ocorrência cada, nunca duplicada.
    assert _db.session.query(Ocorrencia).filter_by(viagem_id=rodada.id).count() == 2
    assert _db.session.query(TelemetriaViagem).filter_by(viagem_id=rodada.id).count() == 1
    assert _registro(_db, rodada, aluno).embarcou is True


def test_duplo_toque_na_primeira_confirmacao_de_presenca_e_idempotente(
    app, _db, aluno, rota_aluno, viagem_futura_agendada_com_motorista, dia_operacao, rota_ponto
):
    viagem_id = viagem_futura_agendada_com_motorista.id
    corpo = {"confirmacao": True, "ponto_embarque_id": str(rota_ponto.ponto_id)}

    def confirmar():
        return app.test_client().put(
            f"/v1/viagens/{viagem_id}/confirmacao", json=corpo, headers=aluno.headers
        )

    respostas = ao_mesmo_tempo(app, [confirmar, confirmar])

    assert status_de(respostas) == [200, 200]
    assert respostas[0].get_json() == respostas[1].get_json()
    _db.session.expire_all()
    registro = _db.session.get(AlunosConfirmados, (viagem_id, aluno.user.id))
    assert registro.confirmacao is True
