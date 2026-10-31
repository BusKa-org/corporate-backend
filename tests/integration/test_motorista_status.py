import threading
from contextlib import contextmanager
from datetime import UTC, date, datetime, timedelta
from zoneinfo import ZoneInfo

from sqlalchemy import event

from app.models.enum import StatusMotorista, StatusViagem
from app.models.user import Motorista
from app.models.viagem import Viagem
from app.services import viagens_service
from app.services.viagens_service import status_motorista
from tests.factories.user_factory import MotoristaFactory
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


def _status(_db, motorista_id):
    return status_motorista(_recarregar(_db, motorista_id), datetime.now(UTC))


def _dados_motorista(gestor, motorista_id):
    r = gestor.client.get(f"/v1/users/{motorista_id}")
    assert r.status_code == 200, r.get_json()
    return r.get_json()


@contextmanager
def _sql_executado(_db):
    """Collect every SQL statement sent to the database inside the block."""
    comandos: list[str] = []

    def registrar(conn, cursor, statement, parameters, context, executemany):
        comandos.append(statement.strip().upper())

    engine = _db.engine
    event.listen(engine, "before_cursor_execute", registrar)
    try:
        yield comandos
    finally:
        event.remove(engine, "before_cursor_execute", registrar)


def _escritas(comandos):
    escritas = []
    for comando in comandos:
        if comando.startswith(("INSERT", "UPDATE", "DELETE")):
            escritas.append(comando)
    return escritas


def test_motorista_novo_esta_ativo_e_aparece_na_resposta(_db, gestor, motorista):
    assert _status(_db, motorista.user.id) == StatusMotorista.ATIVO

    body = _dados_motorista(gestor, motorista.user.id)
    assert body["status_motorista"] == "ATIVO"
    assert body["descanso_ate"] is None

    r = gestor.client.get("/v1/users/motoristas")
    assert r.status_code == 200, r.get_json()
    assert r.get_json()["items"][0]["status_motorista"] == "ATIVO"


def test_iniciar_deixa_em_rota_e_segunda_viagem_e_recusada(
    _db, gestor, motorista, horario_rota, viagem_futura_agendada_com_motorista
):
    r = _acao(motorista, viagem_futura_agendada_com_motorista, "INICIAR")
    assert r.status_code == 200, r.get_json()
    assert _status(_db, motorista.user.id) == StatusMotorista.EM_ROTA
    assert _dados_motorista(gestor, motorista.user.id)["status_motorista"] == "EM_ROTA"

    outra = _nova_viagem(_db, horario_rota, motorista.user.id)
    r = _acao(motorista, outra, "INICIAR")

    assert r.status_code == 409
    assert "em rota" in r.get_json()["error"]["message"]
    _db.session.expire_all()
    assert _db.session.get(Viagem, outra.id).status == StatusViagem.AGENDADA


def test_iniciar_limpa_descanso_vencido(_db, motorista, viagem_futura_agendada_com_motorista):
    motorista.user.descanso_ate = datetime.now(UTC) - timedelta(seconds=1)
    _db.session.commit()

    r = _acao(motorista, viagem_futura_agendada_com_motorista, "INICIAR")

    assert r.status_code == 200, r.get_json()
    m = _recarregar(_db, motorista.user.id)
    assert m.descanso_ate is None
    assert status_motorista(m, datetime.now(UTC)) == StatusMotorista.EM_ROTA


def test_finalizar_viagem_curta_volta_a_ativo(_db, motorista, viagem_futura_agendada_com_motorista):
    assert _acao(motorista, viagem_futura_agendada_com_motorista, "INICIAR").status_code == 200
    r = _acao(motorista, viagem_futura_agendada_com_motorista, "FINALIZAR")

    assert r.status_code == 200, r.get_json()
    assert _recarregar(_db, motorista.user.id).descanso_ate is None
    assert _status(_db, motorista.user.id) == StatusMotorista.ATIVO


def test_finalizar_apos_horas_max_entra_em_descanso(app, _db, motorista, horario_rota):
    inicio = datetime.now(UTC) - timedelta(hours=4, minutes=1)
    viagem = _nova_viagem(
        _db, horario_rota, motorista.user.id, status=StatusViagem.EM_ANDAMENTO, inicio_real=inicio
    )

    r = _acao(motorista, viagem, "FINALIZAR")

    assert r.status_code == 200, r.get_json()
    m = _recarregar(_db, motorista.user.id)
    _db.session.refresh(viagem)
    descanso = timedelta(minutes=app.config["MOTORISTA_DESCANSO_MINUTOS"])
    assert m.descanso_ate == viagem.fim_real + descanso
    assert status_motorista(m, datetime.now(UTC)) == StatusMotorista.EM_DESCANSO_OBRIGATORIO


def test_iniciar_em_descanso_antes_do_fim_e_bloqueado_com_horario(
    app, _db, motorista, viagem_futura_agendada_com_motorista
):
    descanso_ate = datetime.now(UTC) + timedelta(minutes=20)
    motorista.user.descanso_ate = descanso_ate
    _db.session.commit()

    r = _acao(motorista, viagem_futura_agendada_com_motorista, "INICIAR")

    assert r.status_code == 403
    horario = descanso_ate.astimezone(ZoneInfo(app.config["TIMEZONE"])).strftime("%H:%M")
    assert f"Poderá dirigir novamente às {horario}" in r.get_json()["error"]["message"]
    assert _status(_db, motorista.user.id) == StatusMotorista.EM_DESCANSO_OBRIGATORIO


def test_iniciar_um_segundo_antes_do_fim_do_descanso_e_bloqueado(
    monkeypatch, _db, motorista, viagem_futura_agendada_com_motorista
):
    descanso_ate = datetime(2026, 1, 5, 15, 0, tzinfo=UTC)
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
    motorista.user.descanso_ate = descanso_ate
    _db.session.commit()
    monkeypatch.setattr(viagens_service, "_agora", lambda: descanso_ate)

    r = _acao(motorista, viagem_futura_agendada_com_motorista, "INICIAR")

    assert r.status_code == 200, r.get_json()
    assert _status(_db, motorista.user.id) == StatusMotorista.EM_ROTA
    _db.session.refresh(viagem_futura_agendada_com_motorista)
    assert viagem_futura_agendada_com_motorista.inicio_real == descanso_ate


def test_leitura_mostra_ativo_quando_descanso_venceu(_db, gestor, motorista):
    motorista.user.descanso_ate = datetime.now(UTC) - timedelta(minutes=1)
    _db.session.commit()

    body = _dados_motorista(gestor, motorista.user.id)

    assert body["status_motorista"] == "ATIVO"
    assert body["descanso_ate"] is None


def test_leitura_mostra_descanso_enquanto_vale(_db, gestor, motorista):
    descanso_ate = datetime.now(UTC) + timedelta(minutes=10)
    motorista.user.descanso_ate = descanso_ate
    _db.session.commit()

    body = _dados_motorista(gestor, motorista.user.id)

    assert body["status_motorista"] == "EM_DESCANSO_OBRIGATORIO"
    assert datetime.fromisoformat(body["descanso_ate"]) == descanso_ate


def test_cancelar_viagem_iniciada_grava_descanso(_db, gestor, motorista, horario_rota):
    inicio = datetime.now(UTC) - timedelta(hours=4, minutes=5)
    viagem = _nova_viagem(
        _db, horario_rota, motorista.user.id, status=StatusViagem.EM_ANDAMENTO, inicio_real=inicio
    )

    r = gestor.client.put(f"/v1/viagens/{viagem.id}/cancelar")

    assert r.status_code == 200, r.get_json()
    _db.session.refresh(viagem)
    m = _recarregar(_db, motorista.user.id)
    assert viagem.fim_real is not None
    assert m.descanso_ate == viagem.fim_real + timedelta(minutes=30)
    assert status_motorista(m, datetime.now(UTC)) == StatusMotorista.EM_DESCANSO_OBRIGATORIO


def test_cancelar_viagem_curta_iniciada_volta_a_ativo(
    _db, gestor, motorista, viagem_futura_agendada_com_motorista
):
    assert _acao(motorista, viagem_futura_agendada_com_motorista, "INICIAR").status_code == 200

    r = gestor.client.put(f"/v1/viagens/{viagem_futura_agendada_com_motorista.id}/cancelar")

    assert r.status_code == 200, r.get_json()
    assert _status(_db, motorista.user.id) == StatusMotorista.ATIVO


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

    r = gestor.client.put(f"/v1/viagens/{viagem_futura_agendada_com_motorista.id}/cancelar")

    assert r.status_code == 200, r.get_json()
    assert _status(_db, motorista.user.id) == StatusMotorista.EM_ROTA
    _db.session.refresh(em_andamento)
    assert em_andamento.status == StatusViagem.EM_ANDAMENTO


def test_viagem_ativa_apagada_ou_cancelada_le_ativo_sem_escrever(
    _db, gestor, motorista, viagem_futura_iniciada_com_motorista
):
    assert _dados_motorista(gestor, motorista.user.id)["status_motorista"] == "EM_ROTA"

    # Correção manual de dado: a viagem ativa é cancelada direto no banco
    viagem_futura_iniciada_com_motorista.status = StatusViagem.CANCELADA
    _db.session.commit()

    with _sql_executado(_db) as comandos:
        body = _dados_motorista(gestor, motorista.user.id)
        r = gestor.client.get("/v1/users/motoristas")

    assert body["status_motorista"] == "ATIVO"
    assert r.get_json()["items"][0]["status_motorista"] == "ATIVO"
    assert _escritas(comandos) == []

    # ... ou apagada
    _db.session.delete(viagem_futura_iniciada_com_motorista)
    _db.session.commit()
    assert _dados_motorista(gestor, motorista.user.id)["status_motorista"] == "ATIVO"


def test_get_de_usuarios_nao_escreve_no_banco(_db, gestor, motorista, horario_rota):
    _nova_viagem(
        _db,
        horario_rota,
        motorista.user.id,
        status=StatusViagem.EM_ANDAMENTO,
        inicio_real=datetime.now(UTC),
    )

    with _sql_executado(_db) as comandos:
        assert gestor.client.get(f"/v1/users/{motorista.user.id}").status_code == 200
        assert gestor.client.get("/v1/users/motoristas").status_code == 200
        assert gestor.client.get("/v1/users").status_code == 200
        assert motorista.client.get("/v1/users/me").status_code == 200

    assert len(comandos) > 0
    assert _escritas(comandos) == []


def test_listas_usam_numero_fixo_de_queries(_db, gestor, motorista, horario_rota):
    def contar_queries(url):
        with _sql_executado(_db) as comandos:
            r = gestor.client.get(url)
        assert r.status_code == 200
        motoristas = 0
        for item in r.get_json()["items"]:
            if item["role"] == "MOTORISTA":
                motoristas += 1
        return len(comandos), motoristas

    antes = {}
    for url in ("/v1/users/motoristas", "/v1/users"):
        queries, total = contar_queries(url)
        assert total == 1
        antes[url] = queries

    for i in range(4):
        m = MotoristaFactory(organizacao_id=gestor.user.organizacao_id)
        _db.session.add(m)
        _db.session.commit()
        if i % 2 == 0:
            _nova_viagem(
                _db,
                horario_rota,
                m.id,
                status=StatusViagem.EM_ANDAMENTO,
                inicio_real=datetime.now(UTC),
            )

    for url in ("/v1/users/motoristas", "/v1/users"):
        queries, total = contar_queries(url)
        assert total == 5
        assert queries == antes[url], url


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
    assert _status(_db, motorista.user.id) == StatusMotorista.ATIVO


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
    assert m.descanso_ate is None
    assert status_motorista(m, datetime.now(UTC)) == StatusMotorista.ATIVO


def test_iniciar_mesma_viagem_duas_vezes_e_recusado(
    _db, motorista, viagem_futura_agendada_com_motorista
):
    assert _acao(motorista, viagem_futura_agendada_com_motorista, "INICIAR").status_code == 200

    r = _acao(motorista, viagem_futura_agendada_com_motorista, "INICIAR")

    assert r.status_code == 400
    assert _status(_db, motorista.user.id) == StatusMotorista.EM_ROTA


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
        if _db.session.get(Viagem, viagem_id).status == StatusViagem.EM_ANDAMENTO:
            em_andamento += 1
    assert em_andamento == 1
