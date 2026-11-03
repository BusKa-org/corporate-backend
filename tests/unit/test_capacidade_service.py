"""RF-13/RF-14/RF-19: capacity check per segment.

The fixtures' circuit has four stops (P1..P4), so three segments. The vehicle
capacity is forced in each test, because the factory picks a random one.
"""

from datetime import UTC, datetime, timedelta

import pytest

from app.core.exceptions import ConflictError, ForbiddenError, NotFoundError, ValidationError
from app.models.enum import StatusSolicitacao, StatusViagem
from app.models.viagem import SolicitacaoViagem
from app.services import solicitacoes_service
from app.services.capacidade_service import capacidade_viagem, validar_e_reservar, vetor_carga
from tests.conftest import reservar_trajeto
from tests.factories.user_factory import AlunoFactory


@pytest.fixture()
def buffer_aberto(_db, viagem_buffer_aberto, onibus):
    """Trip with the buffer open and capacity 2, to fit the test."""
    onibus.capacidade = 2
    _db.session.commit()
    return viagem_buffer_aberto


@pytest.fixture()
def alunos(_db, organizacao):
    """Enough students to fill both seats twice."""
    turma = [AlunoFactory(organizacao_id=organizacao.id) for _ in range(6)]
    _db.session.add_all(turma)
    _db.session.commit()
    return turma


def _ultima(_db, viagem, aluno_id) -> SolicitacaoViagem:
    return (
        _db.session.query(SolicitacaoViagem)
        .filter_by(viagem_id=viagem.id, aluno_id=aluno_id)
        .order_by(SolicitacaoViagem.created_at.desc())
        .first()
    )


def test_capacidade_vem_do_veiculo_da_viagem(app, _db, buffer_aberto):
    with app.app_context():
        assert capacidade_viagem(buffer_aberto.id) == 2


def test_vetor_comeca_zerado_com_um_slot_por_segmento(app, _db, buffer_aberto):
    with app.app_context():
        assert vetor_carga(buffer_aberto.id) == [0, 0, 0]


def test_assento_e_reusado_por_trajetos_disjuntos(app, _db, buffer_aberto, pontos_circuito, alunos):
    """With capacity 2: P1->P2 twice and P2->P3 twice all fit, because the seat frees
    up at drop-off. A third on P1->P2 does not fit.
    """
    p1, p2, p3, _ = pontos_circuito

    with app.app_context():
        for aluno in alunos[:2]:
            reservar_trajeto(_db, buffer_aberto, aluno.id, p1.id, p2.id)
        for aluno in alunos[2:4]:
            reservar_trajeto(_db, buffer_aberto, aluno.id, p2.id, p3.id)

        assert vetor_carga(buffer_aberto.id) == [2, 2, 0]

        with pytest.raises(ConflictError):
            reservar_trajeto(_db, buffer_aberto, alunos[4].id, p1.id, p2.id)


def test_pico_igual_a_capacidade_nega(app, _db, buffer_aberto, pontos_circuito, alunos):
    """Accepts only if PicoTrecho < capacity; equality already denies."""
    p1, _, _, p4 = pontos_circuito

    with app.app_context():
        reservar_trajeto(_db, buffer_aberto, alunos[0].id, p1.id, p4.id)
        reservar_trajeto(_db, buffer_aberto, alunos[1].id, p1.id, p4.id)
        assert vetor_carga(buffer_aberto.id) == [2, 2, 2]

        with pytest.raises(ConflictError):
            reservar_trajeto(_db, buffer_aberto, alunos[2].id, p1.id, p4.id)


def test_negacao_fica_gravada_como_negado(app, _db, buffer_aberto, pontos_circuito, alunos):
    """RF-21 counts denials per stop, so the denied row has to persist."""
    p1, p2, _, _ = pontos_circuito

    with app.app_context():
        for aluno in alunos[:2]:
            reservar_trajeto(_db, buffer_aberto, aluno.id, p1.id, p2.id)

        with pytest.raises(ConflictError):
            reservar_trajeto(_db, buffer_aberto, alunos[2].id, p1.id, p2.id)

        registro = _ultima(_db, buffer_aberto, alunos[2].id)
        assert registro is not None
        assert registro.status == StatusSolicitacao.NEGADA
        assert registro.ponto_embarque_id == p1.id


def test_origem_depois_do_destino_e_recusada(app, _db, buffer_aberto, pontos_circuito, alunos):
    p1, _, p3, _ = pontos_circuito

    with app.app_context():
        with pytest.raises(ValidationError):
            reservar_trajeto(_db, buffer_aberto, alunos[0].id, p3.id, p1.id)


def test_origem_igual_ao_destino_e_recusada(app, _db, buffer_aberto, pontos_circuito, alunos):
    p1, _, _, _ = pontos_circuito

    with app.app_context():
        with pytest.raises(ValidationError):
            reservar_trajeto(_db, buffer_aberto, alunos[0].id, p1.id, p1.id)


def test_ponto_fora_do_circuito_e_recusado(app, _db, buffer_aberto, pontos_circuito, alunos, ponto):
    p1, _, _, _ = pontos_circuito

    with app.app_context():
        with pytest.raises(ValidationError):
            reservar_trajeto(_db, buffer_aberto, alunos[0].id, p1.id, ponto.id)


def test_buffer_expirado_bloqueia_declaracao(app, _db, buffer_aberto, pontos_circuito, alunos):
    """RF-13, secondary flow 2: an expired timer ends the round."""
    p1, p2, _, _ = pontos_circuito
    buffer_aberto.buffer_fim = datetime.now(UTC) - timedelta(seconds=1)
    _db.session.commit()

    with app.app_context():
        with pytest.raises(ValidationError):
            reservar_trajeto(_db, buffer_aberto, alunos[0].id, p1.id, p2.id)


def test_rodada_fora_do_buffer_bloqueia_declaracao(
    app, _db, buffer_aberto, pontos_circuito, alunos
):
    p1, p2, _, _ = pontos_circuito
    buffer_aberto.status = StatusViagem.EM_ANDAMENTO
    _db.session.commit()

    with app.app_context():
        with pytest.raises(ValidationError):
            reservar_trajeto(_db, buffer_aberto, alunos[0].id, p1.id, p2.id)


def test_aluno_de_outra_organizacao_e_recusado(
    app, _db, buffer_aberto, pontos_circuito, other_aluno
):
    p1, p2, _, _ = pontos_circuito

    with app.app_context():
        with pytest.raises(ForbiddenError):
            reservar_trajeto(_db, buffer_aberto, other_aluno.user.id, p1.id, p2.id)


def test_liberar_devolve_a_capacidade_do_trecho(app, _db, buffer_aberto, pontos_circuito, alunos):
    """RF-19: once the request is cancelled, whoever had been denied now fits."""
    p1, p2, _, _ = pontos_circuito

    with app.app_context():
        for aluno in alunos[:2]:
            reservar_trajeto(_db, buffer_aberto, aluno.id, p1.id, p2.id)

        with pytest.raises(ConflictError):
            reservar_trajeto(_db, buffer_aberto, alunos[2].id, p1.id, p2.id)

        solicitacoes_service.cancelar_solicitacao(str(alunos[0].id), str(buffer_aberto.id))
        assert vetor_carga(buffer_aberto.id) == [1, 0, 0]

        aceito = reservar_trajeto(_db, buffer_aberto, alunos[2].id, p1.id, p2.id)
        assert aceito.status == StatusSolicitacao.ATIVA
        assert vetor_carga(buffer_aberto.id) == [2, 0, 0]


def test_declarar_sem_solicitacao_levanta_not_found(
    app, _db, buffer_aberto, pontos_circuito, alunos
):
    p1, p2, _, _ = pontos_circuito
    with app.app_context():
        with pytest.raises(NotFoundError):
            validar_e_reservar(buffer_aberto.id, alunos[0].id, p1.id, p2.id)


def test_redeclarar_nao_concorre_com_a_propria_reserva(
    app, _db, buffer_aberto, pontos_circuito, alunos
):
    """Changing route must not collide with the seat the student already holds."""
    p1, p2, p3, _ = pontos_circuito

    with app.app_context():
        reservar_trajeto(_db, buffer_aberto, alunos[0].id, p1.id, p2.id)
        reservar_trajeto(_db, buffer_aberto, alunos[1].id, p1.id, p2.id)

        movido = reservar_trajeto(_db, buffer_aberto, alunos[0].id, p1.id, p3.id)
        assert movido.status == StatusSolicitacao.ATIVA
        assert vetor_carga(buffer_aberto.id) == [2, 1, 0]


def test_redeclaracao_negada_preserva_a_reserva_ja_confirmada(
    app, _db, buffer_aberto, pontos_circuito, alunos
):
    """Asking for a full leg must not cost the seat the student already had.

    Regression: the original version overwrote the row with NEGADO, so the student
    left the round for trying to change route.
    """
    p1, p2, p3, p4 = pontos_circuito

    with app.app_context():
        reservar_trajeto(_db, buffer_aberto, alunos[0].id, p1.id, p2.id)
        # Fill P3->P4, which the new route would cross.
        reservar_trajeto(_db, buffer_aberto, alunos[1].id, p3.id, p4.id)
        reservar_trajeto(_db, buffer_aberto, alunos[2].id, p3.id, p4.id)

        with pytest.raises(ConflictError):
            reservar_trajeto(_db, buffer_aberto, alunos[0].id, p1.id, p4.id)

        mantida = _ultima(_db, buffer_aberto, alunos[0].id)
        assert mantida.status == StatusSolicitacao.ATIVA
        assert mantida.ponto_embarque_id == p1.id
        assert mantida.ponto_destino_id == p2.id
        assert vetor_carga(buffer_aberto.id) == [1, 0, 2]


def test_primeira_declaracao_negada_fica_registrada_como_negado(
    app, _db, buffer_aberto, pontos_circuito, alunos
):
    """Whoever has no seat yet leaves a trace of the denial; that is what RF-21 counts."""
    p1, p2, _, _ = pontos_circuito

    with app.app_context():
        reservar_trajeto(_db, buffer_aberto, alunos[0].id, p1.id, p2.id)
        reservar_trajeto(_db, buffer_aberto, alunos[1].id, p1.id, p2.id)

        with pytest.raises(ConflictError):
            reservar_trajeto(_db, buffer_aberto, alunos[2].id, p1.id, p2.id)

        negada = _ultima(_db, buffer_aberto, alunos[2].id)
        assert negada.status == StatusSolicitacao.NEGADA
        assert negada.ponto_embarque_id == p1.id
