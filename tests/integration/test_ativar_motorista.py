from app.models.enum import UserStatus
from tests.factories.user_factory import GestorFactory, MotoristaFactory


def _novo_motorista(_db, organizacao_id):
    m = MotoristaFactory(organizacao_id=organizacao_id, status=UserStatus.PENDING_SIGNUP)
    _db.session.add(m)
    _db.session.commit()
    return m


def _ativar(actor, motorista_id):
    return actor.client.post(f"/v1/users/motoristas/{motorista_id}/ativar")


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


def test_ativar_motorista_pendente_de_aprovacao(_db, gestor, organizacao):
    m = _novo_motorista(_db, organizacao.id)
    m.status = UserStatus.PENDING_APPROVAL
    _db.session.commit()

    r = _ativar(gestor, m.id)

    assert r.status_code == 200, r.get_json()
    assert r.get_json()["status"] == "ACTIVE"
    # The driver did not finish the signup; activation does not pretend it did.
    _db.session.refresh(m)
    assert m.signup_completed_at is None


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
