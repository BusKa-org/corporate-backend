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
    """O contrato de erro precisa valer em produção, não só com DEBUG ligado.

    O flask_restx trata as exceções levantadas dentro dos Resources com o
    próprio handler, que devolve 500 genérico, e só delega para os
    @app.errorhandler do Flask quando PROPAGATE_EXCEPTIONS é verdadeiro. Esse
    valor cai para DEBUG or TESTING quando não é definido, então o resto da
    suíte nunca exercita o comportamento real de produção: todo erro de
    negócio (400, 401, 403, 404) virava 500 na VM.
    """
    monkeypatch.setitem(app.config, "DEBUG", False)
    monkeypatch.setitem(app.config, "TESTING", False)

    r = client.post("/v1/auth/login", json={"email": "naoexiste@buska.test", "password": "errada"})

    assert r.status_code == 401, "erro de negócio não pode virar 500 em produção"
    assert (r.get_json() or {}).get("error", {}).get("code") == "UNAUTHORIZED"
