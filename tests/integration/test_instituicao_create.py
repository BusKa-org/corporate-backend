import pytest


def _payload(tipo: str) -> dict:
    return {
        "nome": "Parque Tecnológico da Paraíba",
        "cnpj": "12345678000199",
        "tipo": tipo,
        "endereco": {
            "logradouro": "Rua Emiliano Rosendo Silva",
            "numero": "115",
            "bairro": "Bodocongó",
            "cidade": "Campina Grande",
            "cep": "58431000",
            "latitude": -7.2141,
            "longitude": -35.9089,
        },
    }


@pytest.mark.integration
def test_create_instituicao_tipo_valido(gestor):
    r = gestor.client.post("/v1/instituicoes/", json=_payload("INSTITUTO_FEDERAL"))
    assert r.status_code == 201, r.get_json()
    assert r.get_json()["tipo"] == "Instituto Federal"


@pytest.mark.integration
def test_create_instituicao_tipo_corporativo(gestor):
    r = gestor.client.post("/v1/instituicoes/", json=_payload("PARQUE_TECNOLOGICO"))
    assert r.status_code == 201, r.get_json()
    assert r.get_json()["tipo"] == "Parque Tecnológico"


@pytest.mark.integration
def test_create_instituicao_sem_latitude_retorna_400(gestor):
    payload = _payload("ESCOLA_PUBLICA")
    del payload["endereco"]["latitude"]
    r = gestor.client.post("/v1/instituicoes/", json=payload)
    assert r.status_code == 400


@pytest.mark.integration
def test_create_instituicao_cnpj_duplicado_retorna_409(gestor):
    primeira = gestor.client.post("/v1/instituicoes/", json=_payload("ESCOLA_PUBLICA"))
    assert primeira.status_code == 201

    segunda = gestor.client.post("/v1/instituicoes/", json=_payload("ESCOLA_PUBLICA"))
    assert segunda.status_code == 409


@pytest.mark.integration
def test_create_instituicao_cnpj_de_outra_organizacao_retorna_409(gestor, other_gestor):
    primeira = gestor.client.post("/v1/instituicoes/", json=_payload("ESCOLA_PUBLICA"))
    assert primeira.status_code == 201

    segunda = other_gestor.client.post("/v1/instituicoes/", json=_payload("ESCOLA_PUBLICA"))
    assert segunda.status_code == 409
    # The raw database error must not reach the client.
    assert "IntegrityError" not in segunda.get_data(as_text=True)
