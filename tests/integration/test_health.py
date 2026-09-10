"""O único teste que faz sentido antes de existir domínio: o factory sobe."""


def test_health(client):
    resp = client.get("/health")
    assert resp.status_code == 200
    assert resp.get_json()["status"] == "ok"


def test_docs_available(client):
    assert client.get("/docs").status_code == 200
