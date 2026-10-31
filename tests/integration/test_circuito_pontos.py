"""RF-04 — gestão dos pontos de parada ordenados do circuito."""

from app.models.rota import RotaPonto


def _ordens(client, rota_id):
    r = client.get(f"/v1/rotas/{rota_id}/pontos")
    assert r.status_code == 200, r.get_data(as_text=True)
    return [p["ordem"] for p in r.get_json()["items"]]


def test_gestor_define_sequencia_gap_free(gestor, circuito, pontos_circuito):
    """A ordem enviada é só preferência: o que persiste é 1..n sem buracos."""
    payload = {
        "pontos": [
            {"ponto_id": str(pontos_circuito[2].id), "ordem": 50},
            {"ponto_id": str(pontos_circuito[0].id), "ordem": 10},
            {"ponto_id": str(pontos_circuito[1].id), "ordem": 30},
        ]
    }
    r = gestor.client.post(f"/v1/rotas/{circuito.id}/pontos", json=payload)
    assert r.status_code == 200, r.get_data(as_text=True)

    itens = gestor.client.get(f"/v1/rotas/{circuito.id}/pontos").get_json()["items"]
    assert [p["ordem"] for p in itens] == [1, 2, 3]
    assert [p["id"] for p in itens] == [
        str(pontos_circuito[0].id),
        str(pontos_circuito[1].id),
        str(pontos_circuito[2].id),
    ]


def test_remover_ponto_renumera_a_sequencia(gestor, _db, circuito, pontos_circuito):
    alvo = pontos_circuito[1]

    r = gestor.client.delete(f"/v1/rotas/{circuito.id}/pontos/{alvo.id}")
    assert r.status_code == 200, r.get_data(as_text=True)

    assert _ordens(gestor.client, circuito.id) == [1, 2, 3]
    assert _db.session.get(RotaPonto, (circuito.id, alvo.id)) is None


def test_remover_ponto_inexistente_na_rota_da_404(gestor, circuito, ponto):
    r = gestor.client.delete(f"/v1/rotas/{circuito.id}/pontos/{ponto.id}")
    assert r.status_code == 404


def test_gestor_de_outra_organizacao_nao_remove_ponto(other_gestor, circuito, pontos_circuito):
    r = other_gestor.client.delete(f"/v1/rotas/{circuito.id}/pontos/{pontos_circuito[0].id}")
    assert r.status_code == 403


def test_viagem_ativa_bloqueia_remocao_do_ponto(gestor, circuito, pontos_circuito, viagem_ociosa):
    """Fluxo secundário 1: a alteração espera a viagem em curso terminar."""
    r = gestor.client.delete(f"/v1/rotas/{circuito.id}/pontos/{pontos_circuito[0].id}")
    assert r.status_code == 409

    assert _ordens(gestor.client, circuito.id) == [1, 2, 3, 4]


def test_viagem_ativa_bloqueia_resequenciar_o_circuito(
    gestor, circuito, pontos_circuito, viagem_ociosa
):
    payload = {"pontos": [{"ponto_id": str(pontos_circuito[0].id), "ordem": 1}]}
    r = gestor.client.post(f"/v1/rotas/{circuito.id}/pontos", json=payload)
    assert r.status_code == 409

    assert _ordens(gestor.client, circuito.id) == [1, 2, 3, 4]


def test_viagem_ativa_bloqueia_edicao_do_ponto(gestor, pontos_circuito, viagem_ociosa):
    r = gestor.client.put(f"/v1/pontos/{pontos_circuito[0].id}", json={"apelido": "Novo apelido"})
    assert r.status_code == 409


def test_viagem_ativa_bloqueia_exclusao_do_ponto(gestor, pontos_circuito, viagem_ociosa):
    r = gestor.client.delete(f"/v1/pontos/{pontos_circuito[0].id}")
    assert r.status_code == 409


def test_ponto_fora_de_viagem_ativa_pode_ser_editado(gestor, ponto):
    r = gestor.client.put(f"/v1/pontos/{ponto.id}", json={"apelido": "Portaria"})
    assert r.status_code == 200, r.get_data(as_text=True)
    assert r.get_json()["apelido"] == "Portaria"
