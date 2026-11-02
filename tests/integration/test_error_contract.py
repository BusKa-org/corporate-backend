import pytest


@pytest.mark.integration
def test_error_contract_validation(client):
    r = client.post("/v1/auth/login", json={})
    assert r.status_code == 400
    body = r.get_json() or {}

    assert "error" in body
    assert body["error"]["code"] == "VALIDATION_ERROR"
    assert isinstance(body["error"]["message"], str)


@pytest.mark.integration
def test_error_contract_unauthorized(client):
    r = client.get("/v1/users")
    assert r.status_code in (401, 422)
    body = r.get_json() or {}

    assert "error" in body
    assert body["error"]["code"] == "UNAUTHORIZED"
    assert isinstance(body["error"]["message"], str)


@pytest.mark.integration
def test_error_contract_sem_debug_nem_testing(app, client, monkeypatch):
    """The error contract must hold in production, not only with DEBUG on.

    flask_restx handles exceptions raised inside Resources with its own handler
    (generic 500) and only delegates to Flask's @app.errorhandler when
    PROPAGATE_EXCEPTIONS is true. That value falls back to DEBUG or TESTING, so
    the rest of the suite never exercises the real production behavior.
    """
    monkeypatch.setitem(app.config, "DEBUG", False)
    monkeypatch.setitem(app.config, "TESTING", False)

    r = client.post("/v1/auth/login", json={"email": "naoexiste@buska.test", "password": "errada"})

    assert r.status_code == 401, "erro de negócio não pode virar 500 em produção"
    assert (r.get_json() or {}).get("error", {}).get("code") == "UNAUTHORIZED"
