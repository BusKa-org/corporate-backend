"""Gestor splits the organization's alunos into projetos."""

import uuid

import pytest

from app.models.enum import UserStatus
from app.models.projeto import Projeto

URL = "/v1/projetos"


def _criar(gestor, nome="Projeto Alfa"):
    resp = gestor.client.post(URL, json={"nome": nome})
    assert resp.status_code == 201, resp.get_json()
    return resp.get_json()


def _definir(gestor, aluno_id, projeto_id):
    return gestor.client.put(f"/v1/alunos/{aluno_id}/projeto", json={"projeto_id": projeto_id})


def _ids_listados(gestor, projeto_id):
    resp = gestor.client.get(f"/v1/alunos/?projeto_id={projeto_id}")
    assert resp.status_code == 200, resp.get_json()
    ids = []
    for item in resp.get_json()["items"]:
        ids.append(item["id"])
    return ids


@pytest.mark.integration
def test_gestor_cria_e_lista_so_os_projetos_da_organizacao(gestor, other_gestor):
    criado = _criar(gestor, "  Projeto Alfa  ")
    _criar(other_gestor, "Projeto da outra")

    assert criado["nome"] == "Projeto Alfa"
    assert criado["ativo"] is True

    body = gestor.client.get(URL).get_json()
    assert body["total"] == 1
    assert body["items"][0]["id"] == criado["id"]


@pytest.mark.integration
def test_nome_repetido_na_mesma_organizacao_da_409(gestor, other_gestor):
    _criar(gestor, "Projeto Alfa")

    resp = gestor.client.post(URL, json={"nome": "projeto alfa"})
    assert resp.status_code == 409
    assert resp.get_json()["error"]["code"] == "CONFLICT"

    # Same name in another organization is fine.
    _criar(other_gestor, "Projeto Alfa")


@pytest.mark.integration
def test_nome_vazio_da_400(gestor):
    assert gestor.client.post(URL, json={"nome": "   "}).status_code == 400
    assert gestor.client.post(URL, json={}).status_code == 400


@pytest.mark.integration
def test_renomear_e_desativar(gestor):
    projeto = _criar(gestor, "Projeto Alfa")
    _criar(gestor, "Projeto Beta")
    url = f"{URL}/{projeto['id']}"

    resp = gestor.client.patch(url, json={"nome": "Projeto Gama"})
    assert resp.status_code == 200
    assert resp.get_json()["nome"] == "Projeto Gama"

    # Changing only the case of its own name is not a conflict.
    assert gestor.client.patch(url, json={"nome": "PROJETO GAMA"}).status_code == 200
    assert gestor.client.patch(url, json={"nome": "projeto beta"}).status_code == 409

    resp = gestor.client.patch(url, json={"ativo": False})
    assert resp.status_code == 200
    assert resp.get_json()["ativo"] is False

    assert gestor.client.patch(url, json={}).status_code == 400


@pytest.mark.integration
def test_projeto_de_outra_organizacao_da_404(gestor, other_gestor, aluno):
    alheio = _criar(other_gestor, "Projeto da outra")

    assert gestor.client.patch(f"{URL}/{alheio['id']}", json={"ativo": False}).status_code == 404
    assert _definir(gestor, aluno.user.id, alheio["id"]).status_code == 404
    assert gestor.client.get(f"/v1/alunos/?projeto_id={alheio['id']}").status_code == 404
    assert gestor.client.patch(f"{URL}/{uuid.uuid4()}", json={"ativo": False}).status_code == 404


@pytest.mark.integration
def test_id_invalido_da_400(gestor, aluno):
    assert gestor.client.patch(f"{URL}/nao-e-uuid", json={"ativo": False}).status_code == 400
    assert _definir(gestor, aluno.user.id, "nao-e-uuid").status_code == 400
    assert gestor.client.get("/v1/alunos/?projeto_id=nao-e-uuid").status_code == 400


@pytest.mark.integration
def test_quem_nao_e_gestor_recebe_403(gestor, aluno, motorista):
    projeto = _criar(gestor)

    for ator in (aluno, motorista):
        assert ator.client.get(URL).status_code == 403
        assert ator.client.post(URL, json={"nome": "X"}).status_code == 403
        assert ator.client.patch(f"{URL}/{projeto['id']}", json={"ativo": False}).status_code == 403
        assert _definir(ator, aluno.user.id, projeto["id"]).status_code == 403


@pytest.mark.integration
def test_gestor_nao_ativo_so_le(gestor, aluno, _db):
    projeto = _criar(gestor)
    gestor.user.status = UserStatus.PENDING_SIGNUP
    _db.session.commit()

    assert gestor.client.get(URL).status_code == 200
    assert gestor.client.post(URL, json={"nome": "Outro"}).status_code == 403
    assert gestor.client.patch(f"{URL}/{projeto['id']}", json={"nome": "X"}).status_code == 403
    assert _definir(gestor, aluno.user.id, projeto["id"]).status_code == 403
    assert _db.session.get(Projeto, uuid.UUID(projeto["id"])).nome == "Projeto Alfa"


@pytest.mark.integration
def test_vincular_desvincular_e_filtrar_alunos(gestor, aluno, aluno_pending):
    alfa = _criar(gestor, "Projeto Alfa")
    beta = _criar(gestor, "Projeto Beta")

    resp = _definir(gestor, aluno.user.id, alfa["id"])
    assert resp.status_code == 200
    assert resp.get_json()["projeto_id"] == alfa["id"]
    assert resp.get_json()["projeto"] == "Projeto Alfa"
    assert _definir(gestor, aluno_pending.user.id, beta["id"]).status_code == 200

    assert _ids_listados(gestor, alfa["id"]) == [str(aluno.user.id)]
    assert _ids_listados(gestor, beta["id"]) == [str(aluno_pending.user.id)]
    assert gestor.client.get("/v1/alunos/").get_json()["total"] == 2

    resp = _definir(gestor, aluno.user.id, None)
    assert resp.status_code == 200
    assert resp.get_json()["projeto_id"] is None
    assert _ids_listados(gestor, alfa["id"]) == []


@pytest.mark.integration
def test_aluno_de_outra_organizacao_da_404(gestor, other_aluno):
    projeto = _criar(gestor)
    assert _definir(gestor, other_aluno.user.id, projeto["id"]).status_code == 404
    assert _definir(gestor, uuid.uuid4(), projeto["id"]).status_code == 404


@pytest.mark.integration
def test_projeto_desativado_nao_recebe_aluno_mas_mantem_os_que_tem(gestor, aluno, aluno_pending):
    projeto = _criar(gestor)
    assert _definir(gestor, aluno.user.id, projeto["id"]).status_code == 200
    gestor.client.patch(f"{URL}/{projeto['id']}", json={"ativo": False})

    assert _definir(gestor, aluno_pending.user.id, projeto["id"]).status_code == 400
    assert _ids_listados(gestor, projeto["id"]) == [str(aluno.user.id)]
