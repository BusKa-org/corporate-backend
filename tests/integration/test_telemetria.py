"""RF-22 — testes de ingestão e consulta de telemetria da bateria."""

from datetime import UTC, datetime, timedelta

from app.models.telemetria import TelemetriaVeiculo

BASE = "/v1/telemetria"


def _amostra(ts: datetime, **campos):
    return {"timestamp": ts.isoformat(), "nivel_bateria": 80.0, **campos}


def _lote(onibus, ts_base: datetime, n: int = 3, **campos):
    return {
        "veiculo_id": str(onibus.id),
        "amostras": [_amostra(ts_base + timedelta(minutes=i), **campos) for i in range(n)],
    }


def test_ingestao_armazena_todas_as_amostras(app, _db, motorista, onibus):
    ts = datetime(2026, 5, 1, 12, 0, tzinfo=UTC)
    resp = motorista.client.post(f"{BASE}/ingestao", json=_lote(onibus, ts, 3))

    assert resp.status_code == 201
    assert resp.get_json() == {"recebidas": 3, "armazenadas": 3, "duplicadas": 0}
    with app.app_context():
        assert _db.session.query(TelemetriaVeiculo).count() == 3


def test_reenvio_do_mesmo_lote_e_idempotente(app, _db, motorista, onibus):
    ts = datetime(2026, 5, 1, 12, 0, tzinfo=UTC)
    lote = _lote(onibus, ts, 3)

    motorista.client.post(f"{BASE}/ingestao", json=lote)
    resp = motorista.client.post(f"{BASE}/ingestao", json=lote)

    assert resp.status_code == 201
    assert resp.get_json() == {"recebidas": 3, "armazenadas": 0, "duplicadas": 3}
    with app.app_context():
        assert _db.session.query(TelemetriaVeiculo).count() == 3


def test_bateria_fora_da_faixa_retorna_400(app, _db, motorista, onibus):
    ts = datetime(2026, 5, 1, 12, 0, tzinfo=UTC)
    resp = motorista.client.post(
        f"{BASE}/ingestao",
        json={"veiculo_id": str(onibus.id), "amostras": [_amostra(ts, nivel_bateria=140.0)]},
    )

    assert resp.status_code == 400
    assert resp.get_json()["error"]["code"] == "VALIDATION_ERROR"
    with app.app_context():
        assert _db.session.query(TelemetriaVeiculo).count() == 0


def test_amostra_sem_viagem_e_aceita(app, _db, motorista, onibus):
    """O veículo fora de operação também reporta — `viagem_id` é opcional."""
    ts = datetime(2026, 5, 1, 12, 0, tzinfo=UTC)
    resp = motorista.client.post(
        f"{BASE}/ingestao",
        json={"veiculo_id": str(onibus.id), "amostras": [_amostra(ts)]},
    )

    assert resp.status_code == 201
    with app.app_context():
        registro = _db.session.query(TelemetriaVeiculo).one()
        assert registro.viagem_id is None


def test_ultimo_por_veiculo_retorna_a_leitura_mais_recente(app, _db, motorista, onibus, gestor):
    ts = datetime(2026, 5, 1, 12, 0, tzinfo=UTC)
    motorista.client.post(
        f"{BASE}/ingestao",
        json={
            "veiculo_id": str(onibus.id),
            "amostras": [
                _amostra(ts, nivel_bateria=90.0),
                _amostra(ts + timedelta(minutes=10), nivel_bateria=55.0),
                _amostra(ts + timedelta(minutes=5), nivel_bateria=70.0),
            ],
        },
    )

    resp = gestor.client.get(f"{BASE}/ultimo")

    assert resp.status_code == 200
    body = resp.get_json()
    assert body["total"] == 1
    assert body["items"][0]["nivel_bateria"] == 55.0


def test_serie_filtra_o_periodo_nos_dois_limites(app, _db, motorista, onibus, gestor):
    ts = datetime(2026, 5, 1, 12, 0, tzinfo=UTC)
    motorista.client.post(f"{BASE}/ingestao", json=_lote(onibus, ts, 5))

    # Limites inclusivos: pega da amostra 1 até a 3 (minutos 1, 2 e 3).
    resp = gestor.client.get(
        f"{BASE}/serie",
        query_string={
            "inicio": (ts + timedelta(minutes=1)).isoformat(),
            "fim": (ts + timedelta(minutes=3)).isoformat(),
        },
    )

    assert resp.status_code == 200
    body = resp.get_json()
    assert body["total"] == 3


def test_consumo_por_viagem_agrega_somente_amostras_com_viagem(
    app, _db, motorista, onibus, gestor, viagem_ociosa
):
    ts = datetime(2026, 5, 1, 12, 0, tzinfo=UTC)
    motorista.client.post(
        f"{BASE}/ingestao",
        json={
            "veiculo_id": str(onibus.id),
            "amostras": [
                _amostra(
                    ts,
                    viagem_id=str(viagem_ociosa.id),
                    nivel_bateria=90.0,
                    consumo_kwh=2.0,
                    odometro_km=1000.0,
                ),
                _amostra(
                    ts + timedelta(minutes=10),
                    viagem_id=str(viagem_ociosa.id),
                    nivel_bateria=70.0,
                    consumo_kwh=3.0,
                    odometro_km=1012.0,
                ),
                _amostra(ts + timedelta(minutes=20), nivel_bateria=69.0, consumo_kwh=9.0),
            ],
        },
    )

    resp = gestor.client.get(f"{BASE}/consumo-por-viagem")

    assert resp.status_code == 200
    body = resp.get_json()
    assert body["total"] == 1
    item = body["items"][0]
    assert item["viagem_id"] == str(viagem_ociosa.id)
    assert item["amostras"] == 2
    assert item["consumo_kwh"] == 5.0
    assert item["km"] == 12.0
    assert (item["bateria_max"], item["bateria_min"]) == (90.0, 70.0)


def test_aluno_nao_pode_ler_telemetria(app, _db, aluno):
    for rota in ("/ultimo", "/serie", "/consumo-por-viagem"):
        assert aluno.client.get(f"{BASE}{rota}").status_code == 403


def test_ingestao_exige_autenticacao(client, onibus):
    ts = datetime(2026, 5, 1, 12, 0, tzinfo=UTC)
    assert client.post(f"{BASE}/ingestao", json=_lote(onibus, ts, 1)).status_code == 401
