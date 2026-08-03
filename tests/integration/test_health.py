import pytest


@pytest.mark.integration
def test_health(client):
    r = client.get("/health")
    assert r.status_code == 200
    data = r.get_json()
    assert data["status"] == "ok"
    assert data["service"] == "mebuska-corporate"


@pytest.mark.integration
def test_ready(client):
    r = client.get("/ready")
    assert r.status_code in (200, 503)
    data = r.get_json()
    assert "ready" in data
