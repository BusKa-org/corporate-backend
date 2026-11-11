from datetime import date, timedelta

import pytest

from app.core.exceptions import ForbiddenError, ValidationError
from app.models.enum import StatusSolicitacao, StatusViagem, UserStatus
from app.models.user import User
from app.models.viagem import AlunosConfirmados, SolicitacaoViagem, Viagem
from app.services import solicitacoes_service, viagens_service
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


@pytest.mark.integration
def test_desativar_motorista_padrao_de_rota_retorna_409_com_as_rotas(gestor, motorista, rota):
    r = gestor.client.post(f"/v1/users/{motorista.user.id}/desativar")
    assert r.status_code == 409, r.get_data(as_text=True)
    assert rota.nome in r.get_json()["error"]["message"]


@pytest.mark.integration
def test_viagem_iniciada_ao_travar_a_confirmacao_fixa_retorna_409(
    _db, gestor, aluno, viagem_futura_agendada_com_motorista, monkeypatch
):
    _db.session.add(
        AlunosConfirmadosFactory(
            viagem_id=viagem_futura_agendada_com_motorista.id,
            aluno_id=aluno.user.id,
            confirmacao=True,
        )
    )
    _db.session.commit()
    travar_original = solicitacoes_service.travar_viagens_do_aluno

    def travar_e_iniciar(aluno_id):
        # The trip started (and committed) just before this lock was granted.
        travadas = travar_original(aluno_id)
        for travada in travadas.values():
            travada.status = StatusViagem.EM_ANDAMENTO
        return travadas

    monkeypatch.setattr(solicitacoes_service, "travar_viagens_do_aluno", travar_e_iniciar)

    r = gestor.client.post(f"/v1/users/{aluno.user.id}/desativar")
    assert r.status_code == 409, r.get_data(as_text=True)
    _db.session.expire_all()
    assert _db.session.get(User, aluno.user.id).status == UserStatus.ACTIVE


@pytest.mark.integration
def test_aluno_desativado_nao_confirma_presenca(
    _db, aluno, rota_aluno, rota_ponto, viagem_futura_agendada_com_motorista, dia_operacao, ponto
):
    aluno.user.status = UserStatus.DISABLED
    _db.session.commit()

    with pytest.raises(ForbiddenError):
        viagens_service.confirmar_presenca_aluno(
            str(aluno.user.id),
            viagem_futura_agendada_com_motorista.id,
            {"confirmacao": True, "ponto_embarque_id": ponto.id},
        )


@pytest.mark.integration
def test_gerar_viagem_com_motorista_desativado_e_rejeitada(
    _db, gestor, motorista, rota, dia_operacao
):
    motorista.user.status = UserStatus.DISABLED
    _db.session.commit()

    with pytest.raises(ValidationError, match="sem cadastro ativo"):
        viagens_service.gerar_viagem(
            str(gestor.user.id),
            {"rota_id": rota.id, "data": date(2026, 11, 2), "motorista_id": motorista.user.id},
        )


@pytest.mark.integration
def test_solicitacao_nao_vai_para_motorista_desativado(
    _db, aluno, motorista, rota_sob_demanda, janela, relogio
):
    motorista.user.status = UserStatus.DISABLED
    _db.session.commit()

    r = aluno.client.post(f"/v1/rotas/{rota_sob_demanda.id}/solicitacoes")
    assert r.status_code == 400, r.get_data(as_text=True)
    assert Viagem.query.filter_by(rota_id=rota_sob_demanda.id).count() == 0


@pytest.mark.integration
def test_rodada_sob_demanda_de_ontem_ainda_bloqueia_o_motorista(
    _db, gestor, motorista, viagem_solicitada, relogio
):
    # The round was requested yesterday and never started: it still waits for this driver.
    relogio.avancar(days=1)

    r = gestor.client.post(f"/v1/users/{motorista.user.id}/desativar")
    assert r.status_code == 409, r.get_data(as_text=True)
    assert "Reatribua as viagens futuras" in r.get_json()["error"]["message"]


@pytest.mark.integration
def test_desativar_conta_ja_desativada_nao_trava_viagens(_db, gestor, aluno, monkeypatch):
    aluno.user.status = UserStatus.DISABLED
    _db.session.commit()

    def nao_deveria_travar(aluno_id):
        raise AssertionError("trips locked for an account that is already disabled")

    monkeypatch.setattr(solicitacoes_service, "travar_viagens_do_aluno", nao_deveria_travar)

    r = gestor.client.post(f"/v1/users/{aluno.user.id}/desativar")
    assert r.status_code == 409, r.get_data(as_text=True)


@pytest.mark.integration
def test_motorista_desativado_nao_vira_motorista_padrao_de_rota(_db, gestor, motorista, rota):
    motorista.user.status = UserStatus.DISABLED
    _db.session.commit()

    r = gestor.client.put(
        f"/v1/rotas/{rota.id}", json={"motorista_padrao_id": str(motorista.user.id)}
    )
    assert r.status_code == 400, r.get_data(as_text=True)
    assert r.get_json()["error"]["message"] == "Motorista sem cadastro ativo"

    r = gestor.client.post(
        "/v1/rotas/", json={"nome": "Nova", "motorista_padrao_id": str(motorista.user.id)}
    )
    assert r.status_code == 400, r.get_data(as_text=True)
    assert r.get_json()["error"]["message"] == "Motorista sem cadastro ativo"


@pytest.mark.integration
def test_motorista_de_outra_organizacao_nao_vira_motorista_padrao(gestor, rota, other_motorista):
    r = gestor.client.put(
        f"/v1/rotas/{rota.id}", json={"motorista_padrao_id": str(other_motorista.user.id)}
    )
    assert r.status_code == 400, r.get_data(as_text=True)
