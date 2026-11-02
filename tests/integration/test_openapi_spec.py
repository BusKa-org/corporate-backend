import pytest


@pytest.mark.integration
def test_openapi_spec_so_cita_seguranca_definida(client):
    spec = client.get("/openapi.json").get_json()
    definidas = spec["securityDefinitions"]

    for operacoes in spec["paths"].values():
        for operacao in operacoes.values():
            if not isinstance(operacao, dict):
                continue
            for requisito in operacao.get("security", []):
                for nome in requisito:
                    assert nome in definidas, nome


@pytest.mark.integration
def test_consentimento_registrado_uma_vez(app):
    # Registering a namespace twice creates endpoints suffixed with "_2".
    for regra in app.url_map.iter_rules():
        if regra.endpoint.startswith("consentimento_"):
            assert not regra.endpoint.endswith("_2"), regra.endpoint
