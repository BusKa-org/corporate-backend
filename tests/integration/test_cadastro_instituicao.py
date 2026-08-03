"""RF-02 — autocadastro vinculado a instituição, com aprovação do gestor.

Cobre também o fluxo secundário 2 do RF-01: login bloqueado enquanto o
cadastro está pendente de aprovação.
"""

import uuid

import pytest
from faker import Faker

from app.models.enum import TipoInstituicao, UserStatus
from app.models.geo import Instituicao
from app.models.notificacao import Notificacao
from app.models.user import Aluno, User

fake = Faker("pt_BR")

SENHA = "StrongPass123!"


def _instituicao(_db, organizacao, nome="UFCG", sigla="UFCG"):
    inst = Instituicao(
        id=uuid.uuid4(),
        fonte="MANUAL",
        codigo_externo=uuid.uuid4().hex[:12],
        nome=nome,
        sigla=sigla,
        tipo=TipoInstituicao.UNIVERSIDADE_PUBLICA,
        uf="PB",
        organizacao_id=organizacao.id,
    )
    _db.session.add(inst)
    _db.session.commit()
    return inst


def _payload(instituicao, **overrides):
    data = {
        "nome": "Fulana de Tal",
        "email": f"{uuid.uuid4().hex[:10]}@ufcg.edu.br",
        "password": SENHA,
        "password_confirm": SENHA,
        "cpf": fake.cpf(),
        "instituicao_id": str(instituicao.id),
    }
    data.update(overrides)
    return data


@pytest.fixture()
def instituicao(_db, organizacao):
    return _instituicao(_db, organizacao)


def _signup(client, instituicao, **overrides):
    return client.post("/v1/alunos/signup", json=_payload(instituicao, **overrides))


# ─── Fluxo principal ───────────────────────────────────────────────────────────


@pytest.mark.integration
def test_signup_cria_conta_pendente_vinculada_a_instituicao(client, _db, instituicao):
    r = _signup(client, instituicao)
    assert r.status_code == 201, r.get_data(as_text=True)

    body = r.get_json()
    assert body["status"] == UserStatus.PENDING_APPROVAL.value
    assert body["instituicao_id"] == str(instituicao.id)

    aluno = _db.session.get(Aluno, uuid.UUID(body["id"]))
    assert aluno.status == UserStatus.PENDING_APPROVAL
    assert str(aluno.instituicao_id) == str(instituicao.id)
    # A organização é herdada da instituição escolhida
    assert aluno.organizacao_id == instituicao.organizacao_id


@pytest.mark.integration
def test_signup_notifica_o_gestor_da_organizacao(client, _db, instituicao, gestor):
    r = _signup(client, instituicao)
    assert r.status_code == 201, r.get_data(as_text=True)

    avisos = _db.session.query(Notificacao).filter_by(usuario_id=gestor.user.id).all()
    assert any("aguardando aprovação" in n.titulo for n in avisos), avisos


@pytest.mark.integration
def test_instituicoes_publicas_listam_as_opcoes_do_formulario(client, _db, organizacao):
    _instituicao(_db, organizacao, nome="Parque Exemplo", sigla="PARQUE")
    r = client.get("/v1/instituicoes/public")
    assert r.status_code == 200, r.get_data(as_text=True)
    assert "Parque Exemplo" in [i["nome"] for i in r.get_json()["items"]]


# ─── Fluxo secundário 1 — validações ───────────────────────────────────────────


@pytest.mark.integration
def test_signup_email_duplicado_nao_cria_conta(client, _db, instituicao):
    email = "repetida@ufcg.edu.br"
    assert _signup(client, instituicao, email=email).status_code == 201

    r = _signup(client, instituicao, email=email)
    assert r.status_code == 409, r.get_data(as_text=True)
    assert _db.session.query(User).filter_by(email=email).count() == 1


@pytest.mark.integration
def test_signup_sem_instituicao_e_rejeitado(client, _db, instituicao):
    payload = _payload(instituicao)
    del payload["instituicao_id"]
    r = client.post("/v1/alunos/signup", json=payload)
    assert r.status_code == 400, r.get_data(as_text=True)
    assert _db.session.query(User).count() == 0


@pytest.mark.integration
def test_signup_com_instituicao_inexistente_e_rejeitado(client, _db, instituicao):
    r = _signup(client, instituicao, instituicao_id=str(uuid.uuid4()))
    assert r.status_code == 404, r.get_data(as_text=True)
    assert _db.session.query(User).count() == 0


@pytest.mark.integration
def test_signup_com_confirmacao_de_senha_divergente_e_rejeitado(client, _db, instituicao):
    r = _signup(client, instituicao, password_confirm="OutraSenha123!")
    assert r.status_code == 400, r.get_data(as_text=True)
    assert "password_confirm" in r.get_data(as_text=True)
    assert _db.session.query(User).count() == 0


@pytest.mark.integration
def test_signup_com_email_invalido_e_rejeitado(client, _db, instituicao):
    r = _signup(client, instituicao, email="nao-e-email")
    assert r.status_code == 400, r.get_data(as_text=True)
    assert _db.session.query(User).count() == 0


# ─── Login pendente / aprovado (RF-01 fluxo secundário 2) ──────────────────────


@pytest.mark.integration
def test_login_bloqueado_enquanto_pendente_de_aprovacao(client, instituicao):
    payload = _payload(instituicao)
    assert client.post("/v1/alunos/signup", json=payload).status_code == 201

    r = client.post(
        "/v1/auth/login", json={"email": payload["email"], "password": payload["password"]}
    )
    assert r.status_code == 403, r.get_data(as_text=True)
    assert "pendente de aprovação" in r.get_json()["error"]["message"]


@pytest.mark.integration
def test_aprovacao_habilita_o_login(client, _db, instituicao, gestor):
    payload = _payload(instituicao)
    aluno_id = client.post("/v1/alunos/signup", json=payload).get_json()["id"]

    r = gestor.client.post(f"/v1/alunos/{aluno_id}/aprovar")
    assert r.status_code == 200, r.get_data(as_text=True)
    assert r.get_json()["status"] == UserStatus.ACTIVE.value

    r = client.post(
        "/v1/auth/login", json={"email": payload["email"], "password": payload["password"]}
    )
    assert r.status_code == 200, r.get_data(as_text=True)
    assert r.get_json()["token"]

    avisos = _db.session.query(Notificacao).filter_by(usuario_id=uuid.UUID(aluno_id)).all()
    assert any("Aprovado" in n.titulo for n in avisos), avisos


# ─── Fluxo secundário 2 — rejeição ─────────────────────────────────────────────


@pytest.mark.integration
def test_rejeicao_bloqueia_login_e_registra_o_motivo(client, _db, instituicao, gestor):
    payload = _payload(instituicao)
    aluno_id = client.post("/v1/alunos/signup", json=payload).get_json()["id"]

    motivo = "E-mail não pertence à instituição informada"
    r = gestor.client.post(f"/v1/alunos/{aluno_id}/rejeitar", json={"motivo": motivo})
    assert r.status_code == 200, r.get_data(as_text=True)
    assert r.get_json()["status"] == UserStatus.REJECTED.value

    avisos = _db.session.query(Notificacao).filter_by(usuario_id=uuid.UUID(aluno_id)).all()
    assert any(motivo in n.mensagem for n in avisos), avisos

    # O motivo precisa persistir ao lado do estado: a conta recusada não loga
    # para ler a notificação, então o painel do gestor é quem vai exibi-lo.
    recusado = _db.session.get(User, uuid.UUID(aluno_id))
    assert recusado.status == UserStatus.REJECTED
    assert recusado.motivo_rejeicao == motivo

    r = client.post(
        "/v1/auth/login", json={"email": payload["email"], "password": payload["password"]}
    )
    assert r.status_code == 403, r.get_data(as_text=True)
    # A recusa é distinta de "conta desativada", e o login diz por quê.
    assert motivo in r.get_json()["error"]["message"]


@pytest.mark.integration
def test_rejeicao_sem_motivo_e_rejeitada(client, instituicao, gestor):
    aluno_id = client.post("/v1/alunos/signup", json=_payload(instituicao)).get_json()["id"]
    r = gestor.client.post(f"/v1/alunos/{aluno_id}/rejeitar", json={})
    assert r.status_code == 400, r.get_data(as_text=True)


# ─── Isolamento entre organizações ─────────────────────────────────────────────


@pytest.mark.integration
def test_gestor_de_outra_organizacao_nao_aprova_nem_rejeita(client, _db, instituicao, other_gestor):
    aluno_id = client.post("/v1/alunos/signup", json=_payload(instituicao)).get_json()["id"]

    assert other_gestor.client.post(f"/v1/alunos/{aluno_id}/aprovar").status_code == 403
    r = other_gestor.client.post(f"/v1/alunos/{aluno_id}/rejeitar", json={"motivo": "não"})
    assert r.status_code == 403, r.get_data(as_text=True)

    aluno = _db.session.get(Aluno, uuid.UUID(aluno_id))
    assert aluno.status == UserStatus.PENDING_APPROVAL
