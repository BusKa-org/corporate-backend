import uuid

import pytest

from app.models.enum import UserStatus


@pytest.mark.integration
def test_create_aluno_requires_auth(client):
    payload = {
        "nome": "Aluno",
        "email": "aluno-auth@buska.test",
        "password": "StrongPass123!",
        "cpf": "52998224725",
        "telefone": "83999999999",
    }
    r = client.post("/v1/users/alunos", json=payload)
    assert r.status_code in (401, 422)


@pytest.mark.integration
def test_create_aluno_as_gestor_success(gestor):
    payload = {
        "nome": "Aluno Criado",
        "email": "aluno1@buska.test",
        "password": "StrongPass123!",
        "cpf": "52998224725",
        "telefone": "83999999999",
    }

    r = gestor.client.post("/v1/users/alunos", json=payload)
    assert r.status_code == 201, r.get_data(as_text=True)

    data = r.get_json() or {}
    assert data.get("message") == "Aluno account created with success"

    aluno_id = data.get("id")
    assert aluno_id
    uuid.UUID(aluno_id)


@pytest.mark.integration
def test_create_aluno_forbidden_for_non_gestor(aluno):
    payload = {
        "nome": "Aluno Criado",
        "email": "aluno2@buska.test",
        "password": "StrongPass123!",
        "cpf": "11144477735",
    }

    r = aluno.client.post("/v1/users/alunos", json=payload)
    assert r.status_code == 403


@pytest.mark.integration
def test_create_aluno_multi_tenant_isolated(gestor, other_gestor):
    payload = {
        "nome": "Aluno Tenant A",
        "email": "aluno-tenant-a@buska.test",
        "password": "StrongPass123!",
        "cpf": "98765432100",
    }

    r = gestor.client.post("/v1/users/alunos", json=payload)
    assert r.status_code == 201, r.get_data(as_text=True)
    aluno_id = (r.get_json() or {}).get("id")

    r2 = other_gestor.client.get(f"/v1/users/{aluno_id}")
    assert r2.status_code in (403, 404)


@pytest.mark.integration
def test_create_aluno_sets_pending_signup_status(gestor):
    payload = {
        "nome": "Aluno Pendente",
        "email": "aluno-pending@buska.test",
        "password": "StrongPass123!",
        "cpf": "39053344705",
        "telefone": "83999999999",
    }

    r = gestor.client.post("/v1/users/alunos", json=payload)
    assert r.status_code == 201, r.get_data(as_text=True)

    aluno_id = (r.get_json() or {}).get("id")
    assert aluno_id

    r2 = gestor.client.get(f"/v1/users/{aluno_id}")
    assert r2.status_code == 200, r2.get_data(as_text=True)

    body = r2.get_json() or {}

    assert body.get("status") == UserStatus.PENDING_SIGNUP.value
    assert body.get("signup_completed_at") is None
    assert body.get("email") == payload["email"]


@pytest.mark.integration
def test_pending_aluno_can_view_own_profile_users_me(aluno_pending):
    r = aluno_pending.client.get("/v1/users/me")
    assert r.status_code == 200, r.get_data(as_text=True)

    body = r.get_json() or {}

    assert body.get("status") == UserStatus.PENDING_SIGNUP.value
    assert body.get("signup_completed_at") is None
    assert body.get("email") == aluno_pending.user.email
