import pytest


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
