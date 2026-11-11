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


def test_resolver_com_id_que_nao_e_uuid_devolve_404(gestor):
    response = gestor.client.patch("/v1/ocorrencias/nao-e-uuid/resolver")

    assert response.status_code == 404


def test_aluno_nao_reporta_ocorrencia_em_viagem_de_outra_organizacao(
    aluno, rota, viagem_futura_agendada_com_motorista, other_organizacao, _db
):
    rota.organizacao_id = other_organizacao.id
    _db.session.commit()

    response = aluno.client.post(
        "/v1/ocorrencias/",
        json={"tipo": "ATRASO", "viagem_id": str(viagem_futura_agendada_com_motorista.id)},
    )

    # Same answer as for a trip that does not exist.
    assert response.status_code == 404
    assert _db.session.query(Ocorrencia).count() == 0


def test_aluno_reporta_ocorrencia_em_viagem_da_organizacao(
    aluno, viagem_futura_agendada_com_motorista
):
    viagem_id = str(viagem_futura_agendada_com_motorista.id)

    response = aluno.client.post(
        "/v1/ocorrencias/", json={"tipo": "ATRASO", "viagem_id": viagem_id}
    )

    assert response.status_code == 201
    assert response.get_json()["viagem_id"] == viagem_id


def test_viagem_id_que_nao_e_uuid_devolve_400(aluno, _db):
    response = aluno.client.post(
        "/v1/ocorrencias/", json={"tipo": "ATRASO", "viagem_id": "nao-e-uuid"}
    )

    assert response.status_code == 400
    assert _db.session.query(Ocorrencia).count() == 0


def test_viagem_da_organizacao_sem_rota_usa_o_motorista(
    aluno, viagem_futura_agendada_com_motorista, _db
):
    # The route FKs are ON DELETE SET NULL: a deleted route leaves the trip without one.
    viagem = viagem_futura_agendada_com_motorista
    viagem.rota_id = None
    viagem.horario_rota_id = None
    _db.session.commit()

    response = aluno.client.post(
        "/v1/ocorrencias/", json={"tipo": "ATRASO", "viagem_id": str(viagem.id)}
    )

    assert response.status_code == 201
