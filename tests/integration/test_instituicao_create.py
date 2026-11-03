from types import SimpleNamespace
from unittest.mock import patch

import pytest
from sqlalchemy.exc import IntegrityError

from app.models.base import db
from app.models.geo import Instituicao


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


@pytest.mark.integration
def test_create_instituicao_cnpj_formatado_vira_digitos(gestor):
    payload = _payload("ESCOLA_PUBLICA")
    payload["cnpj"] = "12.345.678/0001-99"
    r = gestor.client.post("/v1/instituicoes/", json=payload)
    assert r.status_code == 201
    assert r.get_json()["cnpj"] == "12345678000199"

    inst = db.session.get(Instituicao, r.get_json()["id"])
    assert inst.codigo_externo == "12345678000199"

    # The same CNPJ without formatting is still a duplicate.
    segunda = gestor.client.post("/v1/instituicoes/", json=_payload("ESCOLA_PUBLICA"))
    assert segunda.status_code == 409


@pytest.mark.integration
def test_create_instituicao_cnpj_curto_retorna_400(gestor):
    payload = _payload("ESCOLA_PUBLICA")
    payload["cnpj"] = "123"
    r = gestor.client.post("/v1/instituicoes/", json=payload)
    assert r.status_code == 400


@pytest.mark.integration
def test_create_instituicao_outra_integrity_error_retorna_500(gestor):
    orig = SimpleNamespace(diag=SimpleNamespace(constraint_name="fk_outra_constraint"))
    erro = IntegrityError("INSERT ...", {}, orig)  # type: ignore[arg-type]

    with patch.object(db.session, "commit", side_effect=erro):
        r = gestor.client.post("/v1/instituicoes/", json=_payload("ESCOLA_PUBLICA"))

    assert r.status_code == 500
    assert "fk_outra_constraint" not in r.get_data(as_text=True)


@pytest.mark.integration
def test_create_instituicao_nome_longo_retorna_400(gestor):
    payload = _payload("ESCOLA_PUBLICA")
    payload["nome"] = "A" * 201
    r = gestor.client.post("/v1/instituicoes/", json=payload)
    assert r.status_code == 400


@pytest.mark.integration
def test_create_instituicao_nome_de_200_cabe_no_apelido(gestor):
    payload = _payload("ESCOLA_PUBLICA")
    payload["nome"] = "A" * 200
    r = gestor.client.post("/v1/instituicoes/", json=payload)
    assert r.status_code == 201, r.get_json()


@pytest.mark.integration
def test_create_instituicao_latitude_fora_do_intervalo_retorna_400(gestor):
    payload = _payload("ESCOLA_PUBLICA")
    payload["endereco"]["latitude"] = 500
    r = gestor.client.post("/v1/instituicoes/", json=payload)
    assert r.status_code == 400


@pytest.mark.integration
def test_create_instituicao_usa_uf_do_endereco(gestor):
    # The gestor's organização is in PB (OrganizacaoFactory).
    payload = _payload("ESCOLA_PUBLICA")
    payload["endereco"]["uf"] = "pe"
    r = gestor.client.post("/v1/instituicoes/", json=payload)
    assert r.status_code == 201, r.get_json()
    assert r.get_json()["uf"] == "PE"


@pytest.mark.integration
def test_create_instituicao_sem_uf_usa_a_da_organizacao(gestor):
    r = gestor.client.post("/v1/instituicoes/", json=_payload("ESCOLA_PUBLICA"))
    assert r.status_code == 201, r.get_json()
    assert r.get_json()["uf"] == "PB"
