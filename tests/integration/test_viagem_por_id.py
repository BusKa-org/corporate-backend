"""GET /v1/viagens/<id>: manager looks up one trip of their organization."""

import uuid


def test_gestor_obtem_viagem_da_propria_organizacao(gestor, viagem_solicitada):
    r = gestor.client.get(f"/v1/viagens/{viagem_solicitada.id}")
    assert r.status_code == 200, r.get_data(as_text=True)
    body = r.get_json()
    assert body["id"] == str(viagem_solicitada.id)
    assert body["status"] == "SOLICITADA"
    assert body["rota_id"] == str(viagem_solicitada.rota_id)


def test_viagem_de_outra_organizacao_retorna_404(other_gestor, viagem_solicitada):
    r = other_gestor.client.get(f"/v1/viagens/{viagem_solicitada.id}")
    assert r.status_code == 404, r.get_data(as_text=True)


def test_viagem_inexistente_retorna_404(gestor):
    r = gestor.client.get(f"/v1/viagens/{uuid.uuid4()}")
    assert r.status_code == 404, r.get_data(as_text=True)
