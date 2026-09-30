from app.models.enum import TipoViagem
from app.models.rota import Rota


def test_rota_padrao_e_fixa_sem_parametros(gestor):
    r = gestor.client.post("/v1/rotas/", json={"nome": "Linha 1"})
    assert r.status_code == 201, r.get_data(as_text=True)
    body = r.get_json()
    assert body["tipo"] == "FIXA"
    assert body["buffer_minutos"] is None
    assert body["prazo_inicio_minutos"] is None


def test_cria_rota_sob_demanda_com_padroes(gestor):
    r = gestor.client.post("/v1/rotas/", json={"nome": "Circuito", "tipo": "SOB_DEMANDA"})
    assert r.status_code == 201, r.get_data(as_text=True)
    body = r.get_json()
    assert body["tipo"] == "SOB_DEMANDA"
    assert body["buffer_minutos"] == 5
    assert body["prazo_inicio_minutos"] == 10


def test_configura_parametros_sob_demanda(gestor, _db):
    r = gestor.client.post(
        "/v1/rotas/",
        json={"nome": "Circuito", "tipo": "SOB_DEMANDA", "buffer_minutos": 3},
    )
    rota_id = r.get_json()["id"]
    assert r.get_json()["buffer_minutos"] == 3

    r = gestor.client.put(f"/v1/rotas/{rota_id}", json={"prazo_inicio_minutos": 20})
    assert r.status_code == 200, r.get_data(as_text=True)

    rota = _db.session.get(Rota, rota_id)
    assert rota.tipo == TipoViagem.SOB_DEMANDA
    assert (rota.buffer_minutos, rota.prazo_inicio_minutos) == (3, 20)


def test_parametros_fora_do_limite_sao_rejeitados(gestor):
    r = gestor.client.post(
        "/v1/rotas/",
        json={"nome": "Circuito", "tipo": "SOB_DEMANDA", "buffer_minutos": 0},
    )
    assert r.status_code == 400


def test_parametros_rejeitados_em_rota_fixa(gestor, rota):
    r = gestor.client.post("/v1/rotas/", json={"nome": "Linha", "buffer_minutos": 5})
    assert r.status_code == 400

    r = gestor.client.put(f"/v1/rotas/{rota.id}", json={"buffer_minutos": 5})
    assert r.status_code == 400


def test_rota_sob_demanda_nao_aceita_grade_de_horarios(gestor):
    horario = {"horario_saida": "08:00", "sentido": "IDA", "dias": ["SEG"]}
    r = gestor.client.post(
        "/v1/rotas/",
        json={"nome": "Circuito", "tipo": "SOB_DEMANDA", "horarios": [horario]},
    )
    assert r.status_code == 400

    rota_id = gestor.client.post(
        "/v1/rotas/", json={"nome": "Circuito", "tipo": "SOB_DEMANDA"}
    ).get_json()["id"]
    r = gestor.client.post(f"/v1/rotas/{rota_id}/horarios", json=horario)
    assert r.status_code == 400
