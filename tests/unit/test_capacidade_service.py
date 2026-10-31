"""RF-13/RF-14/RF-19 — validação de capacidade por segmento.

O circuito das fixtures tem quatro pontos (P1..P4), logo três segmentos. A
capacidade do veículo é forçada em cada teste, porque a fábrica sorteia.
"""

from datetime import UTC, datetime, timedelta

import pytest

from app.core.exceptions import ConflictError, ForbiddenError, NotFoundError, ValidationError
from app.models.enum import StatusSolicitacao, StatusViagem
from app.models.viagem import AlunosConfirmados
from app.services.capacidade_service import (
    capacidade_viagem,
    liberar,
    validar_e_reservar,
    vetor_carga,
)
from tests.factories.user_factory import AlunoFactory


@pytest.fixture()
def buffer_aberto(_db, viagem_ociosa, onibus):
    """Rodada com o buffer aberto e capacidade 2, para caber no teste."""
    onibus.capacidade = 2
    viagem_ociosa.status = StatusViagem.BUFFER_ABERTO
    viagem_ociosa.buffer_expira_em = datetime.now(UTC) + timedelta(minutes=5)
    _db.session.commit()
    return viagem_ociosa


@pytest.fixture()
def alunos(_db, organizacao):
    """Alunos suficientes para lotar os dois assentos duas vezes."""
    turma = [AlunoFactory(organizacao_id=organizacao.id) for _ in range(6)]
    _db.session.add_all(turma)
    _db.session.commit()
    return turma


def test_capacidade_vem_do_veiculo_da_viagem(app, buffer_aberto):
    with app.app_context():
        assert capacidade_viagem(buffer_aberto.id) == 2


def test_vetor_comeca_zerado_com_um_slot_por_segmento(app, buffer_aberto):
    with app.app_context():
        assert vetor_carga(buffer_aberto.id) == [0, 0, 0]


def test_assento_e_reusado_por_trajetos_disjuntos(app, buffer_aberto, pontos_circuito, alunos):
    """Com capacidade 2: P1->P2 duas vezes e P2->P3 duas vezes cabem todas,
    porque o assento se libera no desembarque. A terceira em P1->P2 não cabe."""
    p1, p2, p3, _ = pontos_circuito

    with app.app_context():
        for aluno in alunos[:2]:
            validar_e_reservar(buffer_aberto.id, aluno.id, p1.id, p2.id)
        for aluno in alunos[2:4]:
            validar_e_reservar(buffer_aberto.id, aluno.id, p2.id, p3.id)

        assert vetor_carga(buffer_aberto.id) == [2, 2, 0]

        with pytest.raises(ConflictError):
            validar_e_reservar(buffer_aberto.id, alunos[4].id, p1.id, p2.id)


def test_pico_igual_a_capacidade_nega(app, buffer_aberto, pontos_circuito, alunos):
    """Aceita apenas se PicoTrecho < capacidade — a igualdade já nega."""
    p1, _, _, p4 = pontos_circuito

    with app.app_context():
        validar_e_reservar(buffer_aberto.id, alunos[0].id, p1.id, p4.id)
        validar_e_reservar(buffer_aberto.id, alunos[1].id, p1.id, p4.id)
        assert vetor_carga(buffer_aberto.id) == [2, 2, 2]

        with pytest.raises(ConflictError):
            validar_e_reservar(buffer_aberto.id, alunos[2].id, p1.id, p4.id)


def test_negacao_fica_gravada_como_negado(app, _db, buffer_aberto, pontos_circuito, alunos):
    """RF-21 conta negações por ponto, então a linha negada tem de persistir."""
    p1, p2, _, _ = pontos_circuito

    with app.app_context():
        for aluno in alunos[:2]:
            validar_e_reservar(buffer_aberto.id, aluno.id, p1.id, p2.id)

        with pytest.raises(ConflictError):
            validar_e_reservar(buffer_aberto.id, alunos[2].id, p1.id, p2.id)

        registro = _db.session.get(AlunosConfirmados, (buffer_aberto.id, alunos[2].id))
        assert registro is not None
        assert registro.status == StatusSolicitacao.NEGADO
        assert registro.confirmacao is False
        assert registro.ponto_embarque_id == p1.id


def test_origem_depois_do_destino_e_recusada(app, buffer_aberto, pontos_circuito, alunos):
    p1, _, p3, _ = pontos_circuito

    with app.app_context():
        with pytest.raises(ValidationError):
            validar_e_reservar(buffer_aberto.id, alunos[0].id, p3.id, p1.id)


def test_origem_igual_ao_destino_e_recusada(app, buffer_aberto, pontos_circuito, alunos):
    p1, _, _, _ = pontos_circuito

    with app.app_context():
        with pytest.raises(ValidationError):
            validar_e_reservar(buffer_aberto.id, alunos[0].id, p1.id, p1.id)


def test_ponto_fora_do_circuito_e_recusado(app, buffer_aberto, pontos_circuito, alunos, ponto):
    p1, _, _, _ = pontos_circuito

    with app.app_context():
        with pytest.raises(ValidationError):
            validar_e_reservar(buffer_aberto.id, alunos[0].id, p1.id, ponto.id)


def test_buffer_expirado_bloqueia_declaracao(app, _db, buffer_aberto, pontos_circuito, alunos):
    """RF-13, fluxo secundário 2: temporizador vencido encerra a rodada."""
    p1, p2, _, _ = pontos_circuito
    buffer_aberto.buffer_expira_em = datetime.now(UTC) - timedelta(seconds=1)
    _db.session.commit()

    with app.app_context():
        with pytest.raises(ValidationError):
            validar_e_reservar(buffer_aberto.id, alunos[0].id, p1.id, p2.id)


def test_rodada_fora_do_buffer_bloqueia_declaracao(
    app, _db, buffer_aberto, pontos_circuito, alunos
):
    p1, p2, _, _ = pontos_circuito
    buffer_aberto.status = StatusViagem.EM_ROTA
    _db.session.commit()

    with app.app_context():
        with pytest.raises(ValidationError):
            validar_e_reservar(buffer_aberto.id, alunos[0].id, p1.id, p2.id)


def test_aluno_de_outra_organizacao_e_recusado(app, buffer_aberto, pontos_circuito, other_aluno):
    p1, p2, _, _ = pontos_circuito

    with app.app_context():
        with pytest.raises(ForbiddenError):
            validar_e_reservar(buffer_aberto.id, other_aluno.user.id, p1.id, p2.id)


def test_liberar_devolve_a_capacidade_do_trecho(app, buffer_aberto, pontos_circuito, alunos):
    """RF-19: cancelada a solicitação, quem tinha sido negado passa a caber."""
    p1, p2, _, _ = pontos_circuito

    with app.app_context():
        for aluno in alunos[:2]:
            validar_e_reservar(buffer_aberto.id, aluno.id, p1.id, p2.id)

        with pytest.raises(ConflictError):
            validar_e_reservar(buffer_aberto.id, alunos[2].id, p1.id, p2.id)

        liberar(buffer_aberto.id, alunos[0].id)
        assert vetor_carga(buffer_aberto.id) == [1, 0, 0]

        aceito = validar_e_reservar(buffer_aberto.id, alunos[2].id, p1.id, p2.id)
        assert aceito.status == StatusSolicitacao.CONFIRMADO
        assert vetor_carga(buffer_aberto.id) == [2, 0, 0]


def test_liberar_sem_solicitacao_levanta_not_found(app, buffer_aberto, alunos):
    with app.app_context():
        with pytest.raises(NotFoundError):
            liberar(buffer_aberto.id, alunos[0].id)


def test_redeclarar_nao_concorre_com_a_propria_reserva(app, buffer_aberto, pontos_circuito, alunos):
    """Trocar o trajeto não pode esbarrar no assento que o próprio aluno ocupa."""
    p1, p2, p3, _ = pontos_circuito

    with app.app_context():
        validar_e_reservar(buffer_aberto.id, alunos[0].id, p1.id, p2.id)
        validar_e_reservar(buffer_aberto.id, alunos[1].id, p1.id, p2.id)

        movido = validar_e_reservar(buffer_aberto.id, alunos[0].id, p1.id, p3.id)
        assert movido.status == StatusSolicitacao.CONFIRMADO
        assert vetor_carga(buffer_aberto.id) == [2, 1, 0]


def test_redeclaracao_negada_preserva_a_reserva_ja_confirmada(
    app, _db, buffer_aberto, pontos_circuito, alunos
):
    """Pedir um trecho lotado não pode custar o lugar que o aluno já tinha.

    Regressão: a versão original sobrescrevia a linha com NEGADO, então o
    aluno saía da rodada por ter tentado mudar de trajeto.
    """
    p1, p2, p3, p4 = pontos_circuito

    with app.app_context():
        validar_e_reservar(buffer_aberto.id, alunos[0].id, p1.id, p2.id)
        # Lota P3->P4, que o novo trajeto atravessaria.
        validar_e_reservar(buffer_aberto.id, alunos[1].id, p3.id, p4.id)
        validar_e_reservar(buffer_aberto.id, alunos[2].id, p3.id, p4.id)

        with pytest.raises(ConflictError):
            validar_e_reservar(buffer_aberto.id, alunos[0].id, p1.id, p4.id)

        mantida = _db.session.get(AlunosConfirmados, (buffer_aberto.id, alunos[0].id))
        assert mantida.status == StatusSolicitacao.CONFIRMADO
        assert mantida.ponto_embarque_id == p1.id
        assert mantida.ponto_destino_id == p2.id
        assert vetor_carga(buffer_aberto.id) == [1, 0, 2]


def test_primeira_declaracao_negada_fica_registrada_como_negado(
    app, _db, buffer_aberto, pontos_circuito, alunos
):
    """Quem ainda não tem lugar deixa rastro da negação — é o que o RF-21 conta."""
    p1, p2, _, _ = pontos_circuito

    with app.app_context():
        validar_e_reservar(buffer_aberto.id, alunos[0].id, p1.id, p2.id)
        validar_e_reservar(buffer_aberto.id, alunos[1].id, p1.id, p2.id)

        with pytest.raises(ConflictError):
            validar_e_reservar(buffer_aberto.id, alunos[2].id, p1.id, p2.id)

        negada = _db.session.get(AlunosConfirmados, (buffer_aberto.id, alunos[2].id))
        assert negada.status == StatusSolicitacao.NEGADO
        assert negada.ponto_embarque_id == p1.id
