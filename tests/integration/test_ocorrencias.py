"""Incident resolution stays inside the manager's organization."""

from app.models.enum import StatusOcorrencia
from app.models.ocorrencia import Ocorrencia


def _criar_ocorrencia(aluno) -> str:
    response = aluno.client.post("/v1/ocorrencias/", json={"tipo": "ATRASO"})
    assert response.status_code == 201
    return response.get_json()["id"]


def test_gestor_de_outra_organizacao_nao_resolve_ocorrencia(aluno, other_gestor, _db):
    ocorrencia_id = _criar_ocorrencia(aluno)

    response = other_gestor.client.patch(f"/v1/ocorrencias/{ocorrencia_id}/resolver")

    # Same answer as for an id that does not exist: listing hides other organizations' incidents.
    assert response.status_code == 404
    _db.session.expire_all()
    assert _db.session.get(Ocorrencia, ocorrencia_id).status == StatusOcorrencia.ABERTA


def test_gestor_da_organizacao_resolve_ocorrencia(aluno, gestor, _db):
    ocorrencia_id = _criar_ocorrencia(aluno)

    response = gestor.client.patch(f"/v1/ocorrencias/{ocorrencia_id}/resolver")

    assert response.status_code == 200
    assert response.get_json()["status"] == StatusOcorrencia.RESOLVIDA.value
