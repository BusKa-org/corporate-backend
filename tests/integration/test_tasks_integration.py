"""Integration tests for the trip reminder jobs on the real database."""

from datetime import UTC, date, datetime, time

import pytest

from app.models.notificacao import Notificacao
from app.tasks.notificacao_tasks import verificar_viagens_10min, verificar_viagens_24h
from tests.factories.rota_factory import RotaAlunoFactory
from tests.factories.viagem_factory import ViagemFactory

# Trip at 08:00 Sao Paulo time (UTC-3) on 2026-11-03, that is 11:00 UTC.
DATA_VIAGEM = date(2026, 11, 3)


@pytest.fixture()
def viagem_8h(_db, horario_rota, motorista, aluno):
    horario_rota.horario_saida = time(8, 0)
    _db.session.add(RotaAlunoFactory(rota_id=horario_rota.rota_id, aluno_id=aluno.user.id))
    v = ViagemFactory(
        horario_rota_id=horario_rota.id,
        data=DATA_VIAGEM,
        motorista_id=motorista.user.id,
    )
    _db.session.add(v)
    _db.session.commit()
    return v


def _notificacoes(usuario_id) -> int:
    return Notificacao.query.filter_by(usuario_id=usuario_id).count()


def test_aviso_24h_sai_25h_antes_e_so_uma_vez(app, _db, viagem_8h, aluno, relogio):
    relogio.ajustar(datetime(2026, 11, 2, 9, 59, tzinfo=UTC))
    verificar_viagens_24h(app)
    assert _notificacoes(aluno.user.id) == 0

    relogio.ajustar(datetime(2026, 11, 2, 10, 0, tzinfo=UTC))
    verificar_viagens_24h(app)
    assert _notificacoes(aluno.user.id) == 1
    assert viagem_8h.aviso_24h_enviado is True

    relogio.ajustar(datetime(2026, 11, 2, 11, 0, tzinfo=UTC))
    verificar_viagens_24h(app)
    assert _notificacoes(aluno.user.id) == 1


def test_aviso_24h_nao_sai_para_viagem_criada_depois_da_janela(app, _db, viagem_8h, aluno, relogio):
    for agora in (
        datetime(2026, 11, 2, 12, 0, tzinfo=UTC),  # 23h before
        datetime(2026, 11, 3, 10, 30, tzinfo=UTC),  # about to leave
        datetime(2026, 11, 3, 11, 30, tzinfo=UTC),  # already left
    ):
        relogio.ajustar(agora)
        verificar_viagens_24h(app)
    assert _notificacoes(aluno.user.id) == 0
    assert viagem_8h.aviso_24h_enviado is False


def test_aviso_10min_sai_20min_antes_e_so_uma_vez(app, _db, viagem_8h, motorista, relogio):
    relogio.ajustar(datetime(2026, 11, 3, 10, 39, tzinfo=UTC))
    verificar_viagens_10min(app)
    assert _notificacoes(motorista.user.id) == 0

    relogio.ajustar(datetime(2026, 11, 3, 10, 40, tzinfo=UTC))
    verificar_viagens_10min(app)
    assert _notificacoes(motorista.user.id) == 1
    assert viagem_8h.aviso_10min_enviado is True

    relogio.ajustar(datetime(2026, 11, 3, 10, 50, tzinfo=UTC))
    verificar_viagens_10min(app)
    assert _notificacoes(motorista.user.id) == 1


def test_aviso_10min_nao_sai_em_cima_da_partida(app, _db, viagem_8h, motorista, relogio):
    for agora in (
        datetime(2026, 11, 3, 10, 55, tzinfo=UTC),  # 5 min before
        datetime(2026, 11, 3, 11, 5, tzinfo=UTC),  # already left
    ):
        relogio.ajustar(agora)
        verificar_viagens_10min(app)
    assert _notificacoes(motorista.user.id) == 0
    assert viagem_8h.aviso_10min_enviado is False
