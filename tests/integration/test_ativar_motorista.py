import pytest
from flask_jwt_extended import create_access_token

from app.models.enum import UserStatus
from app.services.consentimento_service import CONSENTIMENTO_OBRIGATORIO, VERSAO_TERMO_VIGENTE
from tests.factories.user_factory import SENHA_PADRAO, GestorFactory, MotoristaFactory


def _novo_motorista(_db, organizacao_id):
    m = MotoristaFactory(organizacao_id=organizacao_id, status=UserStatus.PENDING_SIGNUP)
    _db.session.add(m)
    _db.session.commit()
    return m


def _ativar(actor, motorista_id):
    return actor.client.post(f"/v1/users/{motorista_id}/ativar")


def test_gestor_ativa_motorista_recem_criado(gestor):
    r = gestor.client.post(
        "/v1/users/motoristas",
        json={
            "nome": "Motorista Novo",
            "email": "novo.motorista@example.com",
            "cpf": "529.982.247-25",
            "password": "SenhaForte123!",
            "cnh": "12345678901",
            "telefone": "83999990000",
        },
    )
    assert r.status_code == 201, r.get_json()
    motorista_id = r.get_json()["id"]
    assert r.get_json()["status"] == "PENDING_SIGNUP"

    r = _ativar(gestor, motorista_id)

    assert r.status_code == 200, r.get_json()
    assert r.get_json()["status"] == "ACTIVE"


def test_ativar_motorista_ja_ativo_retorna_409(gestor, motorista):
    r = _ativar(gestor, motorista.user.id)

    assert r.status_code == 409


def test_ativar_motorista_de_outra_organizacao_retorna_403(_db, gestor, other_organizacao):
    m = _novo_motorista(_db, other_organizacao.id)

    r = _ativar(gestor, m.id)

    assert r.status_code == 403
    _db.session.refresh(m)
    assert m.status == UserStatus.PENDING_SIGNUP


def test_motorista_nao_pode_ativar_motorista(_db, motorista, organizacao):
    m = _novo_motorista(_db, organizacao.id)

    r = _ativar(motorista, m.id)

    assert r.status_code == 403


def test_ativar_motorista_pendente_de_aprovacao_retorna_409(_db, gestor, organizacao):
    # Nothing sets PENDING_APPROVAL on drivers; only a pending signup is activated.
    m = _novo_motorista(_db, organizacao.id)
    m.status = UserStatus.PENDING_APPROVAL
    _db.session.commit()

    assert _ativar(gestor, m.id).status_code == 409


def test_ativacao_nao_preenche_signup_completed_at(_db, gestor, organizacao):
    m = _novo_motorista(_db, organizacao.id)

    assert _ativar(gestor, m.id).status_code == 200
    # The driver did not finish the signup; activation does not pretend it did.
    _db.session.refresh(m)
    assert m.signup_completed_at is None


def test_motorista_ativado_sem_consentimento_precisa_aceitar_o_termo(app, client, _db, gestor):
    r = gestor.client.post(
        "/v1/users/motoristas",
        json={
            "nome": "Motorista Sem Termo",
            "email": "sem.termo@example.com",
            "cpf": "529.982.247-25",
            "password": "SenhaForte123!",
            "cnh": "12345678901",
            "telefone": "83999990000",
        },
    )
    assert r.status_code == 201, r.get_json()
    motorista_id = r.get_json()["id"]
    assert _ativar(gestor, motorista_id).status_code == 200

    login = client.post(
        "/v1/auth/login", json={"email": "sem.termo@example.com", "password": "SenhaForte123!"}
    )
    assert login.status_code == 200, login.get_json()
    assert login.get_json()["consentimento_pendente"] is True
    headers = {"Authorization": f"Bearer {login.get_json()['token']}"}

    # RF-09: no driver feature before accepting the terms, only profile and consent.
    assert client.get("/v1/viagens/minhas", headers=headers).status_code == 403
    assert client.get("/v1/rotas/", headers=headers).status_code == 403
    assert client.get("/v1/users/me", headers=headers).status_code == 200
    assert client.get("/v1/consentimento", headers=headers).status_code == 200

    aceite = client.post(
        "/v1/consentimento", json={"versao": VERSAO_TERMO_VIGENTE}, headers=headers
    )
    assert aceite.status_code in (200, 201), aceite.get_json()
    assert client.get("/v1/viagens/minhas", headers=headers).status_code == 200


def test_ativar_aluno_ou_gestor_retorna_404(_db, gestor, aluno, organizacao):
    outro_gestor = GestorFactory(organizacao_id=organizacao.id)
    _db.session.add(outro_gestor)
    _db.session.commit()

    assert _ativar(gestor, aluno.user.id).status_code == 404
    assert _ativar(gestor, outro_gestor.id).status_code == 404


def test_ativar_motorista_desativado_retorna_409(_db, gestor, motorista):
    motorista.user.status = UserStatus.DISABLED
    _db.session.commit()

    assert _ativar(gestor, motorista.user.id).status_code == 409


def test_ativar_motorista_excluido_retorna_404(_db, gestor, motorista):
    # Same answer as desativar/reativar: a deleted account is not found.
    motorista.user.status = UserStatus.DELETED
    _db.session.commit()

    assert _ativar(gestor, motorista.user.id).status_code == 404


def test_gestor_nao_ativo_nao_ativa_motorista(_db, gestor, organizacao):
    m = _novo_motorista(_db, organizacao.id)
    gestor.user.status = UserStatus.PENDING_SIGNUP
    _db.session.commit()

    r = _ativar(gestor, m.id)

    assert r.status_code == 403
    _db.session.refresh(m)
    assert m.status == UserStatus.PENDING_SIGNUP


def test_ativar_id_invalido_retorna_400(gestor):
    assert _ativar(gestor, "nao-e-uuid").status_code == 400


@pytest.mark.parametrize("acao", ["desativar", "reativar"])
def test_gestor_nao_ativo_nao_desativa_nem_reativa(_db, gestor, aluno, acao):
    if acao == "reativar":
        aluno.user.status = UserStatus.DISABLED
    status_antes = aluno.user.status
    gestor.user.status = UserStatus.PENDING_SIGNUP
    _db.session.commit()

    r = gestor.client.post(f"/v1/users/{aluno.user.id}/{acao}")

    assert r.status_code == 403
    assert "conta ativa" in r.get_json()["error"]["message"]
    _db.session.refresh(aluno.user)
    assert aluno.user.status == status_antes


def test_gestor_nao_ativo_nao_cadastra_motorista(_db, gestor):
    gestor.user.status = UserStatus.PENDING_SIGNUP
    _db.session.commit()

    r = gestor.client.post(
        "/v1/users/motoristas",
        json={
            "nome": "Motorista Novo",
            "email": "novo.motorista@example.com",
            "cpf": "529.982.247-25",
            "password": "SenhaForte123!",
            "cnh": "12345678901",
            "telefone": "83999990000",
        },
    )

    assert r.status_code == 403


def test_id_invalido_e_400_mesmo_com_gestor_nao_ativo(_db, gestor):
    gestor.user.status = UserStatus.PENDING_SIGNUP
    _db.session.commit()

    assert _ativar(gestor, "nao-e-uuid").status_code == 400


def test_gestor_nao_ativo_nao_convida(_db, gestor):
    gestor.user.status = UserStatus.PENDING_SIGNUP
    _db.session.commit()

    r = gestor.client.post("/v1/convites", json={"convites": [{"email": "x@org.test"}]})

    assert r.status_code == 403
    assert "conta ativa" in r.get_json()["error"]["message"]


@pytest.fixture()
def motorista_sem_termo(app, _db, organizacao):
    m = MotoristaFactory(organizacao_id=organizacao.id)
    _db.session.add(m)
    _db.session.commit()
    with app.app_context():
        token = create_access_token(identity=str(m.id))
    return m, {"Authorization": f"Bearer {token}"}


def test_motorista_sem_termo_cuida_da_propria_conta(client, motorista_sem_termo):
    _, headers = motorista_sem_termo

    r = client.post(
        "/v1/users/change-password",
        json={"current_password": SENHA_PADRAO, "new_password": "OutraSenha123!"},
        headers=headers,
    )
    assert r.status_code == 200, r.get_json()
    r = client.patch("/v1/users/me", json={"nome": "Novo Nome"}, headers=headers)
    assert r.status_code == 200, r.get_json()
    r = client.patch("/v1/users/fcm-token", json={"fcm_token": "abc"}, headers=headers)
    assert r.status_code == 200, r.get_json()


def test_motorista_sem_termo_chega_na_exclusao_de_conta(client, motorista_sem_termo):
    m, headers = motorista_sem_termo

    r = client.delete(
        "/v1/users/me", json={"email": m.email, "senha": SENHA_PADRAO}, headers=headers
    )

    # The deletion rule answers (drivers cannot self-delete), not the consent hook.
    assert r.status_code == 403
    assert r.get_json()["error"]["message"] != CONSENTIMENTO_OBRIGATORIO


def test_liberacao_do_termo_e_por_caminho_exato(client, motorista_sem_termo):
    _, headers = motorista_sem_termo

    r = client.get("/v1/consentimento/outra-coisa", headers=headers)

    assert r.status_code == 403
    assert r.get_json()["error"]["message"] == CONSENTIMENTO_OBRIGATORIO
