"""RF-20 — exclusão de conta e anonimização (Art. 18 LGPD)."""

import pytest

from app.models.consentimento import Consentimento
from app.models.enum import StatusSolicitacao, StatusViagem, UserStatus
from app.models.user import User
from app.models.viagem import AlunosConfirmados
from tests.factories.viagem_factory import AlunosConfirmadosFactory

SENHA = "StrongPass123!"


def _excluir(actor, email=None, password=SENHA):
    return actor.client.delete(
        "/v1/consentimento/conta",
        json={"email": email or actor.user.email, "password": password},
    )


@pytest.mark.integration
def test_exclusao_requer_autenticacao(client):
    r = client.delete("/v1/consentimento/conta", json={"email": "x@buska.test", "password": SENHA})
    assert r.status_code in (401, 422)


@pytest.mark.integration
def test_exclusao_com_senha_errada_nao_apaga_nada(aluno, _db):
    email_original = aluno.user.email

    r = _excluir(aluno, password="SenhaErrada123!")
    assert r.status_code == 401, r.get_data(as_text=True)

    _db.session.expire_all()
    assert _db.session.get(User, aluno.user.id).email == email_original


@pytest.mark.integration
def test_exclusao_com_email_de_outro_titular_falha(aluno, other_aluno):
    r = _excluir(aluno, email=other_aluno.user.email)
    assert r.status_code == 401, r.get_data(as_text=True)


@pytest.mark.integration
def test_exclusao_bloqueada_com_embarque_confirmado_em_viagem_ativa(
    aluno, viagem_futura_agendada_com_motorista, _db
):
    _db.session.add(
        AlunosConfirmadosFactory(
            viagem_id=viagem_futura_agendada_com_motorista.id,
            aluno_id=aluno.user.id,
            status=StatusSolicitacao.CONFIRMADO,
        )
    )
    _db.session.commit()

    r = _excluir(aluno)
    assert r.status_code == 409, r.get_data(as_text=True)
    assert "cancele" in ((r.get_json() or {}).get("error", {}).get("message", "")).lower()


@pytest.mark.integration
def test_exclusao_anonimiza_revoga_e_preserva_historico(
    aluno, viagem_futura_agendada_com_motorista, _db, client
):
    viagem = viagem_futura_agendada_com_motorista
    viagem.status = StatusViagem.FINALIZADA
    _db.session.add(
        AlunosConfirmadosFactory(
            viagem_id=viagem.id,
            aluno_id=aluno.user.id,
            status=StatusSolicitacao.CONFIRMADO,
        )
    )
    _db.session.commit()

    assert aluno.client.post("/v1/consentimento").status_code == 201

    email_original, cpf_original, user_id = aluno.user.email, aluno.user.cpf, aluno.user.id

    r = _excluir(aluno)
    assert r.status_code == 200, r.get_data(as_text=True)

    _db.session.expire_all()
    user = _db.session.get(User, user_id)
    assert user is not None
    assert user.email != email_original
    assert user.cpf != cpf_original
    assert email_original not in user.email
    assert user.nome == "Titular removido"
    assert user.telefone is None
    assert user.fcm_token is None
    assert user.status == UserStatus.DISABLED

    # Consentimentos revogados, mas mantidos como prova.
    consentimentos = _db.session.query(Consentimento).filter_by(usuario_id=user_id).all()
    assert consentimentos and all(c.revogado_em is not None for c in consentimentos)

    # Histórico preservado e ainda contável para o dashboard (RF-21).
    assert _db.session.query(AlunosConfirmados).filter_by(viagem_id=viagem.id).count() == 1

    # Sem acesso: as credenciais antigas não logam mais.
    r_login = client.post("/v1/auth/login", json={"email": email_original, "password": SENHA})
    assert r_login.status_code in (401, 403)


@pytest.mark.integration
def test_duas_exclusoes_seguidas_nao_colidem_nas_constraints(aluno, other_aluno, _db):
    assert _excluir(aluno).status_code == 200
    assert _excluir(other_aluno).status_code == 200

    _db.session.expire_all()
    emails = {
        _db.session.get(User, aluno.user.id).email,
        _db.session.get(User, other_aluno.user.id).email,
    }
    cpfs = {
        _db.session.get(User, aluno.user.id).cpf,
        _db.session.get(User, other_aluno.user.id).cpf,
    }
    assert len(emails) == 2
    assert len(cpfs) == 2
