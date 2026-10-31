"""Tests for the non-raising availability helper (needs the DB for the trip history)."""

from datetime import UTC, datetime, time, timedelta
from zoneinfo import ZoneInfo

from app.models.enum import StatusMotorista, StatusViagem
from app.services.viagens_service import disponibilidade_motorista
from tests.factories.viagem_factory import ViagemFactory


def test_ativo_sem_historico_pode_trabalhar(_db, motorista):
    agora = datetime.now(UTC)
    assert disponibilidade_motorista(motorista.user, agora) == (True, None, None)


def test_em_rota_nao_pode_trabalhar(_db, motorista):
    motorista.user.status_motorista = StatusMotorista.EM_ROTA
    pode, motivo, livre = disponibilidade_motorista(motorista.user, datetime.now(UTC))
    assert pode is False
    assert "em rota" in motivo
    assert livre is None


def test_em_descanso_informa_quando_fica_livre(_db, motorista):
    agora = datetime.now(UTC)
    motorista.user.status_motorista = StatusMotorista.EM_DESCANSO
    motorista.user.descanso_ate = agora + timedelta(minutes=5)

    pode, motivo, livre = disponibilidade_motorista(motorista.user, agora)

    assert pode is False
    assert "Poderá dirigir novamente" in motivo
    assert livre == agora + timedelta(minutes=5)


def test_descanso_termina_exatamente_em_descanso_ate(_db, motorista):
    agora = datetime.now(UTC)
    motorista.user.status_motorista = StatusMotorista.EM_DESCANSO
    motorista.user.descanso_ate = agora

    assert disponibilidade_motorista(motorista.user, agora) == (True, None, None)
    assert disponibilidade_motorista(motorista.user, agora - timedelta(seconds=1))[0] is False


def test_historico_de_direcao_bloqueia_mesmo_ativo(_db, motorista):
    agora = datetime.now(UTC)
    fim = agora - timedelta(minutes=5)
    v = ViagemFactory(
        data=agora.date(),
        status=StatusViagem.FINALIZADA,
        motorista_id=motorista.user.id,
        inicio_real=agora - timedelta(hours=4, minutes=10),
        fim_real=fim,
    )
    _db.session.add(v)
    _db.session.commit()

    pode, _, livre = disponibilidade_motorista(motorista.user, agora)

    assert pode is False
    assert livre == fim + timedelta(minutes=30)


def test_fora_do_dia_de_trabalho(app, _db, motorista):
    # 2026-01-05 é segunda-feira
    agora = datetime(2026, 1, 5, 12, 0, tzinfo=ZoneInfo(app.config["TIMEZONE"]))
    motorista.user.dias_trabalho = ["TER"]

    pode, motivo, livre = disponibilidade_motorista(motorista.user, agora)

    assert pode is False
    assert "dia de trabalho" in motivo
    assert livre is None


def test_turno_que_atravessa_meia_noite(app, _db, motorista):
    fuso = ZoneInfo(app.config["TIMEZONE"])
    motorista.user.horario_inicio = time(22, 0)
    motorista.user.horario_fim = time(6, 0)

    assert disponibilidade_motorista(motorista.user, datetime(2026, 1, 5, 23, 0, tzinfo=fuso))[0]
    assert disponibilidade_motorista(motorista.user, datetime(2026, 1, 5, 5, 59, tzinfo=fuso))[0]
    fora = disponibilidade_motorista(motorista.user, datetime(2026, 1, 5, 6, 0, tzinfo=fuso))
    assert fora[0] is False
    assert "Fora do horário" in fora[1]
