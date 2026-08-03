from tests.helpers.assertions import assert_json_ok


def login_and_get_headers(client, email: str, password: str):
    r = client.post("/v1/auth/login", json={"email": email, "password": password})
    assert r.status_code == 200, r.get_data(as_text=True)
    data = assert_json_ok(r)
    token = data.get("access_token") or data.get("token")
    assert token, f"Token not found in response: {data}"
    return {"Authorization": f"Bearer {token}"}
