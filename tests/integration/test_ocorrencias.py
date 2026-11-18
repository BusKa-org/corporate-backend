"""Incident resolution stays inside the manager's organization."""

from app.models.enum import StatusOcorrencia
from app.models.notificacao import Notificacao
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


def test_gestor_da_organizacao_responde_ocorrencia_e_notifica_o_autor(aluno, gestor, _db):
    ocorrencia_id = _criar_ocorrencia(aluno)

    response = gestor.client.put(
        f"/v1/ocorrencias/{ocorrencia_id}/resposta", json={"resposta": "  Vamos verificar.  "}
    )

    assert response.status_code == 200
    body = response.get_json()
    assert body["resposta"] == "Vamos verificar."
    assert body["respondida_em"] is not None
    ocorrencia = _db.session.get(Ocorrencia, ocorrencia_id)
    assert ocorrencia.respondida_por_id == gestor.user.id
    notificacoes = Notificacao.query.filter_by(usuario_id=aluno.user.id).all()
    assert len(notificacoes) == 1
    assert notificacoes[0].mensagem == "Vamos verificar."


def test_gestor_de_outra_organizacao_nao_responde_ocorrencia(aluno, other_gestor, _db):
    ocorrencia_id = _criar_ocorrencia(aluno)

    response = other_gestor.client.put(
        f"/v1/ocorrencias/{ocorrencia_id}/resposta", json={"resposta": "Intrusa"}
    )

    assert response.status_code == 404
    _db.session.expire_all()
    assert _db.session.get(Ocorrencia, ocorrencia_id).resposta is None


def test_resposta_vazia_ou_acima_do_limite_devolve_400(aluno, gestor, app):
    ocorrencia_id = _criar_ocorrencia(aluno)
    limite = app.config["OCORRENCIA_RESPOSTA_MAX_CARACTERES"]
    url = f"/v1/ocorrencias/{ocorrencia_id}/resposta"

    assert gestor.client.put(url, json={"resposta": "   "}).status_code == 400
    assert gestor.client.put(url, json={"resposta": "x" * (limite + 1)}).status_code == 400


def test_autor_ve_a_resposta_nas_suas_ocorrencias(aluno, other_aluno, gestor):
    ocorrencia_id = _criar_ocorrencia(aluno)
    gestor.client.put(f"/v1/ocorrencias/{ocorrencia_id}/resposta", json={"resposta": "Resolvido."})

    response = aluno.client.get("/v1/ocorrencias/minhas")

    assert response.status_code == 200
    body = response.get_json()
    assert len(body) == 1
    assert body[0]["id"] == ocorrencia_id
    assert body[0]["resposta"] == "Resolvido."
    # Another author never sees this incident.
    assert other_aluno.client.get("/v1/ocorrencias/minhas").get_json() == []


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


def test_viagem_id_em_formato_urn_grava_o_id_da_viagem(
    aluno, viagem_futura_agendada_com_motorista, _db
):
    viagem = viagem_futura_agendada_com_motorista

    response = aluno.client.post(
        "/v1/ocorrencias/", json={"tipo": "ATRASO", "viagem_id": f"urn:uuid:{viagem.id}"}
    )

    assert response.status_code == 201
    ocorrencia = _db.session.get(Ocorrencia, response.get_json()["id"])
    assert ocorrencia.viagem_id == viagem.id
