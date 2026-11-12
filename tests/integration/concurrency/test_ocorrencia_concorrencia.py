"""Incident resolution under concurrency."""

import pytest

from tests.integration.concurrency.conftest import ao_mesmo_tempo, status_de

pytestmark = [pytest.mark.integration, pytest.mark.concurrency]


def test_resolucao_dupla_da_ocorrencia_resolve_uma_vez(app, aluno, gestor):
    response = aluno.client.post("/v1/ocorrencias/", json={"tipo": "ATRASO"})
    assert response.status_code == 201
    ocorrencia_id = response.get_json()["id"]

    def resolver():
        return app.test_client().patch(
            f"/v1/ocorrencias/{ocorrencia_id}/resolver", headers=gestor.headers
        )

    respostas = ao_mesmo_tempo(app, [resolver, resolver])

    # The second waits on the row lock and sees it already resolved.
    assert status_de(respostas) == [200, 400]
