# tests/helpers/assertions.py
def assert_json_ok(resp):
    assert resp.is_json, f"Response is not JSON: {resp.get_data(as_text=True)}"
    return resp.get_json() or {}


def assert_error_response(resp, status_code: int, error_msg: str = None):
    assert resp.status_code == status_code, f"Expected {status_code}, got {resp.status_code}"
    data = assert_json_ok(resp)
    assert "error" in data, f"Error not found in {data}"
    if error_msg:
        assert error_msg in data["error"], f"Error message {error_msg} not found in {data['error']}"
    return data


def assert_validation_error(resp, field: str = None):
    data = assert_error_response(resp, 400)
    if field:
        assert field in str(data), f"Field {field} not found in {data}"
    return data


def assert_requires_auth(resp):
    assert resp.status_code in (401, 403, 422), f"Expected 401, 403, or 422, got {resp.status_code}"
