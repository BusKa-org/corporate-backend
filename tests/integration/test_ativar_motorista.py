from app.models.enum import UserStatus
from tests.factories.user_factory import MotoristaFactory


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
