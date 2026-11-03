import pytest


@pytest.mark.parametrize("metodo", ["get", "patch", "delete"])
def test_id_de_onibus_invalido_retorna_400(gestor, metodo):
    r = getattr(gestor.client, metodo)("/v1/onibus/nao-e-uuid", json={})
    assert r.status_code == 400, r.get_data(as_text=True)
