import pytest

from tests.helpers.assertions import assert_json_ok, assert_requires_auth


@pytest.mark.integration
def test_users_requires_auth(client):
    r = client.get("/v1/users")
    assert_requires_auth(r)


@pytest.mark.integration
def test_users_with_auth(gestor):
    r = gestor.client.get("/v1/users")
    assert r.status_code == 200, r.get_data(as_text=True)
    data = assert_json_ok(r)
    assert data.get("items") is not None
    assert data.get("total") is not None
    assert any(u.get("id") == str(gestor.user.id) for u in data["items"])
