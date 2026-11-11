import pytest

from app.models.enum import UserStatus
from tests.factories.user_factory import SENHA_PADRAO


def _login(client, email):
    return client.post("/v1/auth/login", json={"email": email, "password": SENHA_PADRAO})


@pytest.mark.integration
def test_desativar_bloqueia_login_e_token(client, gestor, aluno):
    r = gestor.client.post(f"/v1/users/{aluno.user.id}/desativar")
    assert r.status_code == 200, r.get_data(as_text=True)
    assert r.get_json()["status"] == UserStatus.DISABLED.value

    assert _login(client, aluno.user.email).status_code == 403
    assert aluno.client.get("/v1/users/me").status_code == 401


@pytest.mark.integration
def test_reativar_libera_login(client, gestor, motorista):
    gestor.client.post(f"/v1/users/{motorista.user.id}/desativar")

    r = gestor.client.post(f"/v1/users/{motorista.user.id}/reativar")
    assert r.status_code == 200, r.get_data(as_text=True)
    assert r.get_json()["status"] == UserStatus.ACTIVE.value
    assert _login(client, motorista.user.email).status_code == 200


@pytest.mark.integration
def test_gestor_nao_desativa_a_propria_conta(gestor):
    r = gestor.client.post(f"/v1/users/{gestor.user.id}/desativar")
    assert r.status_code == 400, r.get_data(as_text=True)


@pytest.mark.integration
def test_somente_gestor_desativa(motorista, aluno):
    r = motorista.client.post(f"/v1/users/{aluno.user.id}/desativar")
    assert r.status_code == 403, r.get_data(as_text=True)


@pytest.mark.integration
def test_gestor_nao_desativa_conta_de_outra_organizacao(gestor, other_aluno):
    r = gestor.client.post(f"/v1/users/{other_aluno.user.id}/desativar")
    assert r.status_code == 403, r.get_data(as_text=True)


@pytest.mark.integration
def test_reativar_conta_ativa_retorna_409(gestor, aluno):
    r = gestor.client.post(f"/v1/users/{aluno.user.id}/reativar")
    assert r.status_code == 409, r.get_data(as_text=True)


@pytest.mark.integration
def test_desativar_conta_pendente_retorna_409(gestor, aluno_pending):
    r = gestor.client.post(f"/v1/users/{aluno_pending.user.id}/desativar")
    assert r.status_code == 409, r.get_data(as_text=True)
