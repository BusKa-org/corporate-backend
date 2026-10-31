from datetime import UTC, datetime, timedelta
from zoneinfo import ZoneInfo

from app.models.enum import StatusViagem
from tests.factories.viagem_factory import ViagemFactory


def _viagem_finalizada(_db, motorista_id, inicio, fim):
    v = ViagemFactory(
        data=inicio.date(),
        status=StatusViagem.FINALIZADA,
        motorista_id=motorista_id,
        inicio_real=inicio,
        fim_real=fim,
    )
    _db.session.add(v)
    _db.session.commit()


def _iniciar(motorista, viagem):
    return motorista.client.put(f"/v1/viagens/{viagem.id}/acao", json={"acao": "INICIAR"})


def test_iniciar_bloqueado_apos_horas_max_de_direcao(
    _db, motorista, viagem_futura_agendada_com_motorista
):
    agora = datetime.now(UTC)
    _viagem_finalizada(
        _db, motorista.user.id, agora - timedelta(hours=4, minutes=10), agora - timedelta(minutes=5)
    )

    r = _iniciar(motorista, viagem_futura_agendada_com_motorista)

    assert r.status_code == 403
    assert "Poderá dirigir novamente" in r.get_json()["error"]["message"]


def test_iniciar_liberado_apos_descanso(_db, motorista, viagem_futura_agendada_com_motorista):
    agora = datetime.now(UTC)
    _viagem_finalizada(
        _db, motorista.user.id, agora - timedelta(hours=5), agora - timedelta(minutes=31)
    )

    r = _iniciar(motorista, viagem_futura_agendada_com_motorista)

    assert r.status_code == 200, r.get_json()


def test_iniciar_bloqueado_fora_do_horario_de_trabalho(
    app, _db, motorista, viagem_futura_agendada_com_motorista
):
    agora_local = datetime.now(ZoneInfo(app.config["TIMEZONE"]))
    motorista.user.horario_inicio = (agora_local + timedelta(hours=1)).time()
    motorista.user.horario_fim = (agora_local + timedelta(hours=2)).time()
    _db.session.commit()

    r = _iniciar(motorista, viagem_futura_agendada_com_motorista)

    assert r.status_code == 403
    assert "Fora do horário de trabalho" in r.get_json()["error"]["message"]


def test_gestor_define_horario_de_trabalho(gestor, motorista):
    r = gestor.client.patch(
        f"/v1/users/motoristas/{motorista.user.id}",
        json={"horario_inicio": "08:00", "horario_fim": "17:00", "dias_trabalho": ["SEG", "QUA"]},
    )

    assert r.status_code == 200, r.get_json()
    body = r.get_json()
    assert body["horario_inicio"].startswith("08:00")
    assert body["horario_fim"].startswith("17:00")
    assert body["dias_trabalho"] == ["SEG", "QUA"]
