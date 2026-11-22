import pytest


@pytest.mark.parametrize(
    "origin_lat, origin_lng",
    [("nan", "-34.86"), ("inf", "-34.86"), ("91", "-34.86"), ("-7.11", "-180.5")],
)
def test_coordenada_nao_finita_ou_fora_do_intervalo_e_recusada(gestor, origin_lat, origin_lng):
    resposta = gestor.client.get(
        f"/v1/routing/route?origin_lat={origin_lat}&origin_lng={origin_lng}"
        "&dest_lat=-7.12&dest_lng=-34.88"
    )
    assert resposta.status_code == 400
