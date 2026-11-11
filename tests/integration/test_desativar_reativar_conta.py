from datetime import timedelta

import pytest

from app.models.enum import StatusSolicitacao, StatusViagem, UserStatus
from app.models.user import User
from app.models.viagem import AlunosConfirmados, SolicitacaoViagem, Viagem
from tests.factories.user_factory import SENHA_PADRAO, AlunoFactory, GestorFactory
from tests.factories.viagem_factory import AlunosConfirmadosFactory, ViagemFactory


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


@pytest.mark.integration
def test_desativar_gestor_ou_conta_excluida_retorna_404(_db, gestor, other_gestor, organizacao):
    outro = GestorFactory(organizacao_id=organizacao.id)
    excluido = AlunoFactory(organizacao_id=organizacao.id, status=UserStatus.DELETED)
    _db.session.add_all([outro, excluido])
    _db.session.commit()

    assert gestor.client.post(f"/v1/users/{outro.id}/desativar").status_code == 404
    assert gestor.client.post(f"/v1/users/{excluido.id}/desativar").status_code == 404


@pytest.mark.integration
def test_outra_organizacao_responde_igual_para_qualquer_conta(gestor, other_gestor, other_aluno):
    # Same 403 for an aluno and a gestor: the role of another org's account does not leak.
    assert gestor.client.post(f"/v1/users/{other_aluno.user.id}/reativar").status_code == 403
    assert gestor.client.post(f"/v1/users/{other_gestor.user.id}/desativar").status_code == 403


@pytest.mark.integration
def test_reativar_conta_pendente_de_aprovacao_retorna_409(_db, gestor, aluno):
    aluno.user.status = UserStatus.PENDING_APPROVAL
    _db.session.commit()

    r = gestor.client.post(f"/v1/users/{aluno.user.id}/reativar")
    assert r.status_code == 409, r.get_data(as_text=True)


@pytest.mark.integration
def test_gestor_nao_reativa_a_propria_conta(gestor):
    r = gestor.client.post(f"/v1/users/{gestor.user.id}/reativar")
    assert r.status_code == 400, r.get_data(as_text=True)


@pytest.mark.integration
def test_id_invalido_retorna_400(gestor):
    assert gestor.client.post("/v1/users/nao-e-uuid/desativar").status_code == 400


@pytest.mark.integration
@pytest.mark.parametrize("quem", ["aluno", "motorista"])
def test_desativar_em_viagem_em_andamento_retorna_409(
    _db, gestor, aluno, motorista, viagem_futura_iniciada_com_motorista, quem
):
    _db.session.add(
        AlunosConfirmadosFactory(
            viagem_id=viagem_futura_iniciada_com_motorista.id,
            aluno_id=aluno.user.id,
            confirmacao=True,
        )
    )
    _db.session.commit()
    alvo = aluno if quem == "aluno" else motorista

    r = gestor.client.post(f"/v1/users/{alvo.user.id}/desativar")
    assert r.status_code == 409, r.get_data(as_text=True)
    _db.session.expire_all()
    assert alvo.user.status == UserStatus.ACTIVE


@pytest.mark.integration
def test_desativar_motorista_com_viagem_futura_retorna_409(
    _db, gestor, motorista, viagem_solicitada, relogio
):
    r = gestor.client.post(f"/v1/users/{motorista.user.id}/desativar")
    assert r.status_code == 409, r.get_data(as_text=True)
    _db.session.expire_all()
    assert motorista.user.status == UserStatus.ACTIVE


@pytest.mark.integration
def test_desativar_motorista_com_janela_retorna_409(gestor, motorista, janela):
    r = gestor.client.post(f"/v1/users/{motorista.user.id}/desativar")
    assert r.status_code == 409, r.get_data(as_text=True)


@pytest.mark.integration
def test_desativar_aluno_libera_solicitacoes_e_confirmacoes(
    _db, gestor, aluno, horario_rota, viagem_solicitada, relogio
):
    agendada = ViagemFactory(
        horario_rota_id=horario_rota.id,
        data=relogio.agora.date() + timedelta(days=1),
        status=StatusViagem.AGENDADA,
    )
    _db.session.add(agendada)
    _db.session.flush()
    _db.session.add(
        AlunosConfirmadosFactory(viagem_id=agendada.id, aluno_id=aluno.user.id, confirmacao=True)
    )
    aluno.user.fcm_token = "token-fcm-de-teste"
    _db.session.commit()

    r = gestor.client.post(f"/v1/users/{aluno.user.id}/desativar")
    assert r.status_code == 200, r.get_data(as_text=True)

    _db.session.expire_all()
    solicitacao = SolicitacaoViagem.query.filter_by(viagem_id=viagem_solicitada.id).one()
    assert solicitacao.status == StatusSolicitacao.CANCELADA
    # Same RF-19 effect as the student cancelling: the trip left with no one is cancelled.
    assert _db.session.get(Viagem, viagem_solicitada.id).status == StatusViagem.CANCELADA
    assert _db.session.get(AlunosConfirmados, (agendada.id, aluno.user.id)).confirmacao is False
    assert _db.session.get(User, aluno.user.id).fcm_token is None
