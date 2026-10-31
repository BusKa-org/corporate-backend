import threading
from datetime import UTC, date, datetime, timedelta
from zoneinfo import ZoneInfo

from app.models.enum import StatusMotorista, StatusViagem
from app.models.user import Motorista
from app.services import viagens_service
from tests.factories.viagem_factory import ViagemFactory


def _acao(motorista, viagem, acao):
    return motorista.client.put(f"/v1/viagens/{viagem.id}/acao", json={"acao": acao})


def _nova_viagem(_db, horario_rota, motorista_id, **kwargs):
    v = ViagemFactory(
        horario_rota_id=horario_rota.id,
        data=date.today() + timedelta(days=7),
        status=kwargs.pop("status", StatusViagem.AGENDADA),
        motorista_id=motorista_id,
        **kwargs,
    )
    _db.session.add(v)
    _db.session.commit()
    return v


def _recarregar(_db, motorista_id):
    _db.session.expire_all()
    return _db.session.get(Motorista, motorista_id)


def _dados_motorista(gestor, motorista_id):
    r = gestor.client.get(f"/v1/users/{motorista_id}")
    assert r.status_code == 200, r.get_json()
    return r.get_json()


def test_motorista_novo_comeca_ativo_e_aparece_na_resposta(_db, gestor, motorista):
    assert motorista.user.status_motorista == StatusMotorista.ATIVO

    body = _dados_motorista(gestor, motorista.user.id)
    assert body["status_motorista"] == "ATIVO"
    assert body["descanso_ate"] is None

    r = gestor.client.get("/v1/users/motoristas")
    assert r.status_code == 200, r.get_json()
    assert r.get_json()["items"][0]["status_motorista"] == "ATIVO"


def test_iniciar_deixa_em_rota_e_segunda_viagem_e_recusada(
    _db, motorista, horario_rota, viagem_futura_agendada_com_motorista
):
    r = _acao(motorista, viagem_futura_agendada_com_motorista, "INICIAR")
    assert r.status_code == 200, r.get_json()
    assert _recarregar(_db, motorista.user.id).status_motorista == StatusMotorista.EM_ROTA

    outra = _nova_viagem(_db, horario_rota, motorista.user.id)
    r = _acao(motorista, outra, "INICIAR")

    assert r.status_code == 409
    assert "em rota" in r.get_json()["error"]["message"]
    _db.session.expire_all()
    assert _db.session.get(type(outra), outra.id).status == StatusViagem.AGENDADA


def test_finalizar_viagem_curta_volta_a_ativo(_db, motorista, viagem_futura_agendada_com_motorista):
    assert _acao(motorista, viagem_futura_agendada_com_motorista, "INICIAR").status_code == 200
    r = _acao(motorista, viagem_futura_agendada_com_motorista, "FINALIZAR")

    assert r.status_code == 200, r.get_json()
    m = _recarregar(_db, motorista.user.id)
    assert m.status_motorista == StatusMotorista.ATIVO
    assert m.descanso_ate is None


def test_finalizar_apos_horas_max_entra_em_descanso(app, _db, motorista, horario_rota):
    inicio = datetime.now(UTC) - timedelta(hours=4, minutes=1)
    viagem = _nova_viagem(
        _db, horario_rota, motorista.user.id, status=StatusViagem.EM_ANDAMENTO, inicio_real=inicio
    )
    motorista.user.status_motorista = StatusMotorista.EM_ROTA
    _db.session.commit()

    r = _acao(motorista, viagem, "FINALIZAR")

    assert r.status_code == 200, r.get_json()
    m = _recarregar(_db, motorista.user.id)
    _db.session.refresh(viagem)
    descanso = timedelta(minutes=app.config["MOTORISTA_DESCANSO_MINUTOS"])
    assert m.status_motorista == StatusMotorista.EM_DESCANSO_OBRIGATORIO
    assert m.descanso_ate == viagem.fim_real + descanso


def test_iniciar_em_descanso_antes_do_fim_e_bloqueado_com_horario(
    app, _db, motorista, viagem_futura_agendada_com_motorista
):
    descanso_ate = datetime.now(UTC) + timedelta(minutes=20)
    motorista.user.status_motorista = StatusMotorista.EM_DESCANSO_OBRIGATORIO
    motorista.user.descanso_ate = descanso_ate
    _db.session.commit()

    r = _acao(motorista, viagem_futura_agendada_com_motorista, "INICIAR")

    assert r.status_code == 403
    horario = descanso_ate.astimezone(ZoneInfo(app.config["TIMEZONE"])).strftime("%H:%M")
    assert f"Poderá dirigir novamente às {horario}" in r.get_json()["error"]["message"]
    assert (
        _recarregar(_db, motorista.user.id).status_motorista
        == StatusMotorista.EM_DESCANSO_OBRIGATORIO
    )


def test_iniciar_apos_fim_do_descanso_e_permitido(
    _db, motorista, viagem_futura_agendada_com_motorista
):
    motorista.user.status_motorista = StatusMotorista.EM_DESCANSO_OBRIGATORIO
    motorista.user.descanso_ate = datetime.now(UTC) - timedelta(seconds=1)
    _db.session.commit()

    r = _acao(motorista, viagem_futura_agendada_com_motorista, "INICIAR")

    assert r.status_code == 200, r.get_json()
    m = _recarregar(_db, motorista.user.id)
    assert m.status_motorista == StatusMotorista.EM_ROTA
    assert m.descanso_ate is None


def test_leitura_mostra_ativo_quando_descanso_venceu(_db, gestor, motorista):
    motorista.user.status_motorista = StatusMotorista.EM_DESCANSO_OBRIGATORIO
    motorista.user.descanso_ate = datetime.now(UTC) - timedelta(minutes=1)
    _db.session.commit()

    body = _dados_motorista(gestor, motorista.user.id)

    assert body["status_motorista"] == "ATIVO"
    assert body["descanso_ate"] is None


def test_leitura_mostra_descanso_enquanto_vale(_db, gestor, motorista):
    descanso_ate = datetime.now(UTC) + timedelta(minutes=10)
    motorista.user.status_motorista = StatusMotorista.EM_DESCANSO_OBRIGATORIO
    motorista.user.descanso_ate = descanso_ate
    _db.session.commit()

    body = _dados_motorista(gestor, motorista.user.id)

    assert body["status_motorista"] == "EM_DESCANSO_OBRIGATORIO"
    assert datetime.fromisoformat(body["descanso_ate"]) == descanso_ate


def test_cancelar_viagem_iniciada_atualiza_status(_db, gestor, motorista, horario_rota):
    inicio = datetime.now(UTC) - timedelta(hours=4, minutes=5)
    viagem = _nova_viagem(
        _db, horario_rota, motorista.user.id, status=StatusViagem.EM_ANDAMENTO, inicio_real=inicio
    )
    motorista.user.status_motorista = StatusMotorista.EM_ROTA
    _db.session.commit()

    r = gestor.client.put(f"/v1/viagens/{viagem.id}/cancelar")

    assert r.status_code == 200, r.get_json()
    m = _recarregar(_db, motorista.user.id)
    _db.session.refresh(viagem)
    assert viagem.fim_real is not None
    assert m.status_motorista == StatusMotorista.EM_DESCANSO_OBRIGATORIO
    assert m.descanso_ate is not None


def test_cancelar_viagem_curta_iniciada_volta_a_ativo(
    _db, gestor, motorista, viagem_futura_agendada_com_motorista
):
    assert _acao(motorista, viagem_futura_agendada_com_motorista, "INICIAR").status_code == 200

    r = gestor.client.put(f"/v1/viagens/{viagem_futura_agendada_com_motorista.id}/cancelar")

    assert r.status_code == 200, r.get_json()
    assert _recarregar(_db, motorista.user.id).status_motorista == StatusMotorista.ATIVO


def test_cancelar_viagem_nao_iniciada_nao_muda_status(
    _db, gestor, motorista, horario_rota, viagem_futura_agendada_com_motorista
):
    em_andamento = _nova_viagem(
        _db,
        horario_rota,
        motorista.user.id,
        status=StatusViagem.EM_ANDAMENTO,
        inicio_real=datetime.now(UTC),
    )
    motorista.user.status_motorista = StatusMotorista.EM_ROTA
    _db.session.commit()

    r = gestor.client.put(f"/v1/viagens/{viagem_futura_agendada_com_motorista.id}/cancelar")

    assert r.status_code == 200, r.get_json()
    assert _recarregar(_db, motorista.user.id).status_motorista == StatusMotorista.EM_ROTA
    _db.session.refresh(em_andamento)
    assert em_andamento.status == StatusViagem.EM_ANDAMENTO


def test_fora_do_horario_bloqueia_mesmo_ativo_e_status_nao_muda(
    app, _db, motorista, viagem_futura_agendada_com_motorista
):
    agora_local = datetime.now(ZoneInfo(app.config["TIMEZONE"]))
    motorista.user.horario_inicio = (agora_local + timedelta(hours=1)).time()
    motorista.user.horario_fim = (agora_local + timedelta(hours=2)).time()
    _db.session.commit()

    r = _acao(motorista, viagem_futura_agendada_com_motorista, "INICIAR")

    assert r.status_code == 403
    assert "Fora do horário de trabalho" in r.get_json()["error"]["message"]
    assert _recarregar(_db, motorista.user.id).status_motorista == StatusMotorista.ATIVO


def test_gestor_nao_altera_status_por_patch(_db, gestor, motorista):
    r = gestor.client.patch(
        f"/v1/users/motoristas/{motorista.user.id}",
        json={
            "nome": "Novo Nome",
            "status_motorista": "EM_DESCANSO_OBRIGATORIO",
            "descanso_ate": "2030-01-01T00:00:00+00:00",
        },
    )

    assert r.status_code == 200, r.get_json()
    assert r.get_json()["status_motorista"] == "ATIVO"
    m = _recarregar(_db, motorista.user.id)
    assert m.nome == "Novo Nome"
    assert m.status_motorista == StatusMotorista.ATIVO
    assert m.descanso_ate is None


def test_iniciar_mesma_viagem_duas_vezes_e_recusado(
    _db, motorista, viagem_futura_agendada_com_motorista
):
    assert _acao(motorista, viagem_futura_agendada_com_motorista, "INICIAR").status_code == 200

    r = _acao(motorista, viagem_futura_agendada_com_motorista, "INICIAR")

    assert r.status_code == 400
    assert _recarregar(_db, motorista.user.id).status_motorista == StatusMotorista.EM_ROTA


def test_dois_inicios_simultaneos_so_um_passa(
    app, _db, motorista, horario_rota, viagem_futura_agendada_com_motorista
):
    outra = _nova_viagem(_db, horario_rota, motorista.user.id)
    viagens = [viagem_futura_agendada_com_motorista.id, outra.id]
    barreira = threading.Barrier(2)
    status_codes: list[int] = []

    def iniciar(viagem_id):
        # Cada thread tem seu cliente, contexto e sessão (conexão) próprios
        cliente = app.test_client()
        barreira.wait()
        r = cliente.put(
            f"/v1/viagens/{viagem_id}/acao", json={"acao": "INICIAR"}, headers=motorista.headers
        )
        status_codes.append(r.status_code)

    threads = []
    for viagem_id in viagens:
        t = threading.Thread(target=iniciar, args=(viagem_id,))
        threads.append(t)
        t.start()
    for t in threads:
        t.join(timeout=30)

    assert sorted(status_codes) == [200, 409]
    _db.session.expire_all()
    em_andamento = 0
    for viagem_id in viagens:
        if _db.session.get(type(outra), viagem_id).status == StatusViagem.EM_ANDAMENTO:
            em_andamento += 1
    assert em_andamento == 1


def test_em_rota_sem_viagem_em_andamento_pode_iniciar(
    _db, motorista, viagem_futura_agendada_com_motorista
):
    motorista.user.status_motorista = StatusMotorista.EM_ROTA
    _db.session.commit()

    r = _acao(motorista, viagem_futura_agendada_com_motorista, "INICIAR")

    assert r.status_code == 200, r.get_json()
    assert _recarregar(_db, motorista.user.id).status_motorista == StatusMotorista.EM_ROTA


def test_em_rota_sem_viagem_e_corrigido_na_leitura(_db, gestor, motorista):
    motorista.user.status_motorista = StatusMotorista.EM_ROTA
    _db.session.commit()

    assert _dados_motorista(gestor, motorista.user.id)["status_motorista"] == "ATIVO"
    assert _recarregar(_db, motorista.user.id).status_motorista == StatusMotorista.ATIVO


def test_em_rota_sem_viagem_mas_com_direcao_longa_vira_descanso_na_leitura(
    _db, gestor, motorista, horario_rota
):
    fim = datetime.now(UTC) - timedelta(minutes=5)
    _nova_viagem(
        _db,
        horario_rota,
        motorista.user.id,
        status=StatusViagem.FINALIZADA,
        inicio_real=fim - timedelta(hours=4),
        fim_real=fim,
    )
    motorista.user.status_motorista = StatusMotorista.EM_ROTA
    _db.session.commit()

    r = gestor.client.get("/v1/users/motoristas")

    assert r.get_json()["items"][0]["status_motorista"] == "EM_DESCANSO_OBRIGATORIO"
    m = _recarregar(_db, motorista.user.id)
    assert m.status_motorista == StatusMotorista.EM_DESCANSO_OBRIGATORIO
    assert m.descanso_ate == fim + timedelta(minutes=30)


def test_em_rota_com_viagem_em_andamento_continua_em_rota(
    _db, gestor, motorista, viagem_futura_iniciada_com_motorista
):
    motorista.user.status_motorista = StatusMotorista.EM_ROTA
    _db.session.commit()

    assert _dados_motorista(gestor, motorista.user.id)["status_motorista"] == "EM_ROTA"


def test_iniciar_um_segundo_antes_do_fim_do_descanso_e_bloqueado(
    monkeypatch, _db, motorista, viagem_futura_agendada_com_motorista
):
    descanso_ate = datetime(2026, 1, 5, 15, 0, tzinfo=UTC)
    motorista.user.status_motorista = StatusMotorista.EM_DESCANSO_OBRIGATORIO
    motorista.user.descanso_ate = descanso_ate
    _db.session.commit()
    monkeypatch.setattr(viagens_service, "_agora", lambda: descanso_ate - timedelta(seconds=1))

    r = _acao(motorista, viagem_futura_agendada_com_motorista, "INICIAR")

    assert r.status_code == 403
    assert "Poderá dirigir novamente" in r.get_json()["error"]["message"]


def test_iniciar_exatamente_no_fim_do_descanso_e_permitido(
    monkeypatch, _db, motorista, viagem_futura_agendada_com_motorista
):
    descanso_ate = datetime(2026, 1, 5, 15, 0, tzinfo=UTC)
    motorista.user.status_motorista = StatusMotorista.EM_DESCANSO_OBRIGATORIO
    motorista.user.descanso_ate = descanso_ate
    _db.session.commit()
    monkeypatch.setattr(viagens_service, "_agora", lambda: descanso_ate)

    r = _acao(motorista, viagem_futura_agendada_com_motorista, "INICIAR")

    assert r.status_code == 200, r.get_json()
    m = _recarregar(_db, motorista.user.id)
    assert m.status_motorista == StatusMotorista.EM_ROTA
    _db.session.refresh(viagem_futura_agendada_com_motorista)
    assert viagem_futura_agendada_com_motorista.inicio_real == descanso_ate
