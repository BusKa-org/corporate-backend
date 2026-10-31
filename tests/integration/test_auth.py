from datetime import date

import pytest

from app.models.enum import UserStatus
from tests.factories.user_factory import SENHA_PADRAO, AlunoFactory


@pytest.mark.integration
def test_login_missing_fields_returns_400(client):
    r = client.post("/v1/auth/login", json={})
    assert r.status_code == 400, r.get_data(as_text=True)
    data = r.get_json() or {}
    assert "error" in data


@pytest.mark.integration
def test_login_invalid_credentials_returns_401(client):
    r = client.post("/v1/auth/login", json={"email": "nope@buska.test", "password": "wrong"})
    assert r.status_code == 401, r.get_data(as_text=True)


@pytest.mark.integration
def test_login_success_returns_token(client, gestor):
    r = client.post(
        "/v1/auth/login", json={"email": gestor.user.email, "password": "StrongPass123!"}
    )
    assert r.status_code == 200, r.get_data(as_text=True)
    data = r.get_json() or {}
    assert data.get("token"), f"Token not found in response: {data}"
    assert data.get("user"), f"User not found in response: {data}"
    assert data.get("user").get("id") == str(
        gestor.user.id
    ), f"User ID mismatch: {data.get('user')}"
    assert (
        data.get("user").get("email") == gestor.user.email
    ), f"User email mismatch: {data.get('user')}"
    assert (
        data.get("user").get("nome") == gestor.user.nome
    ), f"User name mismatch: {data.get('user')}"
    assert data["user"]["role"] == gestor.user.role.value, f"User role mismatch: {data.get('user')}"


@pytest.mark.integration
def test_login_minor_pending_signup_is_not_blocked(client, _db, organizacao):
    # Antes, menor em PENDING_SIGNUP com e-mail do responsável e sem consentimento
    # ficava travado no login para sempre: nenhum fluxo grava mais esse consentimento.
    # As colunas saíram (migration e4f5a6b7c8d9); aqui fica o mesmo cenário sem elas.
    aluno = AlunoFactory(
        organizacao_id=organizacao.id,
        status=UserStatus.PENDING_SIGNUP,
        data_nascimento=date(date.today().year - 15, 1, 1),
    )
    _db.session.add(aluno)
    _db.session.commit()

    r = client.post("/v1/auth/login", json={"email": aluno.email, "password": SENHA_PADRAO})
    assert r.status_code == 200, r.get_data(as_text=True)
