from app.models.enum import UserStatus
from tests.factories.user_factory import MotoristaFactory


def _criar_motorista(_db, organizacao_id, status):
    m = MotoristaFactory(organizacao_id=organizacao_id, status=status)
    _db.session.add(m)
    _db.session.commit()
    return m


def _ids(resposta):
    ids: set[str] = set()
    for item in resposta.get_json()["items"]:
        ids.add(item["id"])
    return ids


def test_gestor_lista_so_os_pendentes_da_propria_organizacao(
    _db, gestor, motorista, organizacao, other_organizacao
):
    pendente = _criar_motorista(_db, organizacao.id, UserStatus.PENDING_SIGNUP)
    _criar_motorista(_db, other_organizacao.id, UserStatus.PENDING_SIGNUP)

    r = gestor.client.get("/v1/users/motoristas?status=PENDING_SIGNUP")

    assert r.status_code == 200, r.get_json()
    assert _ids(r) == {str(pendente.id)}
    assert r.get_json()["total"] == 1


def test_motorista_aprovado_sai_da_lista_de_pendentes(_db, gestor, organizacao):
    pendente = _criar_motorista(_db, organizacao.id, UserStatus.PENDING_SIGNUP)

    assert gestor.client.post(f"/v1/users/{pendente.id}/ativar").status_code == 200

    r = gestor.client.get("/v1/users/motoristas?status=PENDING_SIGNUP")
    assert _ids(r) == set()
    r = gestor.client.get("/v1/users/motoristas?status=ACTIVE")
    assert str(pendente.id) in _ids(r)


def test_status_invalido_retorna_400(gestor):
    assert gestor.client.get("/v1/users/motoristas?status=PENDENTE").status_code == 400


def test_nao_gestor_nao_lista_motoristas(motorista, aluno):
    assert motorista.client.get("/v1/users/motoristas").status_code == 403
    assert aluno.client.get("/v1/users/motoristas").status_code == 403


def test_status_invalido_na_lista_de_alunos_tambem_retorna_400(gestor):
    # Same filter helper as the drivers' list; it used to ignore a typo and list everyone.
    assert gestor.client.get("/v1/alunos/?status=PENDENTE").status_code == 400


def test_status_vazio_lista_todos(gestor, motorista):
    r = gestor.client.get("/v1/users/motoristas?status=")
    assert r.status_code == 200, r.get_json()
    assert str(motorista.user.id) in _ids(r)
    assert gestor.client.get("/v1/alunos/?status=").status_code == 200
