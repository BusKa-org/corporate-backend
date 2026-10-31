"""RF-11 (iniciar percurso), RF-12 (broadcast do buffer) e os jobs do scheduler."""

import uuid
from datetime import timedelta

import pytest

from app.models.consentimento import ACEITE, Consentimento
from app.models.credencial_embarque import CredencialEmbarque
from app.models.enum import StatusMotorista, StatusSolicitacao, StatusViagem, UserStatus
from app.models.notificacao import Notificacao
from app.models.viagem import AlunosConfirmados, Viagem
from app.services import buffer_service, viagens_service
from app.services.consentimento_service import VERSAO_TERMO_VIGENTE
from tests.factories.user_factory import AlunoFactory, GestorFactory, MotoristaFactory


def _url(viagem_id):
    return f"/v1/viagens/{viagem_id}/iniciar-percurso"


def _notificacoes(user_id):
    return Notificacao.query.filter_by(usuario_id=user_id).count()


def _novo_aluno(_db, organizacao_id, consentimento=True, **campos):
    u = AlunoFactory(organizacao_id=organizacao_id, **campos)
    _db.session.add(u)
    _db.session.commit()
    if consentimento:
        _db.session.add(Consentimento(usuario_id=u.id, versao=VERSAO_TERMO_VIGENTE, acao=ACEITE))
        _db.session.commit()
    return u


# --- RF-11: iniciar percurso -------------------------------------------------


def test_outro_motorista_recebe_403(_db, viagem_solicitada, organizacao, client, app):
    from flask_jwt_extended import create_access_token

    outro = MotoristaFactory(organizacao_id=organizacao.id)
    _db.session.add(outro)
    _db.session.commit()
    token = create_access_token(identity=str(outro.id))

    resp = client.post(_url(viagem_solicitada.id), headers={"Authorization": f"Bearer {token}"})

    assert resp.status_code == 403


def test_gestor_recebe_403(gestor, viagem_solicitada):
    assert gestor.client.post(_url(viagem_solicitada.id)).status_code == 403


def test_aluno_recebe_403(aluno, viagem_solicitada):
    assert aluno.client.post(_url(viagem_solicitada.id)).status_code == 403


def test_viagem_inexistente_404(motorista):
    assert motorista.client.post(_url(uuid.uuid4())).status_code == 404


@pytest.mark.parametrize("status", [StatusViagem.BUFFER_ABERTO, StatusViagem.EM_ANDAMENTO])
def test_status_errado_409(_db, motorista, viagem_solicitada, status):
    viagem_solicitada.status = status
    _db.session.commit()

    resp = motorista.client.post(_url(viagem_solicitada.id))

    assert resp.status_code == 409
    assert status.value in resp.get_json()["error"]["message"]


def test_inicia_buffer_com_minutos_da_rota(
    _db, motorista, viagem_solicitada, rota_sob_demanda, relogio
):
    rota_sob_demanda.buffer_minutos = 7
    _db.session.commit()

    resp = motorista.client.post(_url(viagem_solicitada.id))

    assert resp.status_code == 200
    assert resp.get_json()["status"] == StatusViagem.BUFFER_ABERTO.value
    viagem = _db.session.get(Viagem, viagem_solicitada.id)
    _db.session.refresh(viagem)
    assert viagem.status == StatusViagem.BUFFER_ABERTO
    assert viagem.buffer_fim == relogio.agora + timedelta(minutes=7)


# --- RF-12: broadcast --------------------------------------------------------


def test_broadcast_so_para_alunos_aptos_da_org(
    _db, motorista, gestor, aluno, other_aluno, viagem_solicitada, organizacao, relogio
):
    outro_apto = _novo_aluno(_db, organizacao.id)
    sem_consentimento = _novo_aluno(_db, organizacao.id, consentimento=False)
    sem_notificacoes = _novo_aluno(_db, organizacao.id, receber_notificacoes=False)
    desativado = _novo_aluno(_db, organizacao.id, status=UserStatus.DISABLED)

    resp = motorista.client.post(_url(viagem_solicitada.id))
    assert resp.status_code == 200

    assert _notificacoes(aluno.user.id) == 1
    assert _notificacoes(outro_apto.id) == 1
    assert _notificacoes(sem_consentimento.id) == 0
    assert _notificacoes(sem_notificacoes.id) == 0
    assert _notificacoes(desativado.id) == 0
    assert _notificacoes(other_aluno.user.id) == 0
    assert _notificacoes(motorista.user.id) == 0
    assert _notificacoes(gestor.user.id) == 0
    assert "5 minuto" in Notificacao.query.filter_by(usuario_id=aluno.user.id).one().mensagem


# --- Job: fechar buffers expirados --------------------------------------------


def _abrir_buffer(_db, viagem, buffer_fim):
    viagem.status = StatusViagem.BUFFER_ABERTO
    viagem.buffer_fim = buffer_fim
    _db.session.commit()


def test_buffer_expirado_vira_em_andamento(
    _db, viagem_solicitada, circuito, pontos_circuito, motorista, aluno, relogio
):
    solicitacao = viagem_solicitada.solicitacoes[0]
    solicitacao.ponto_embarque_id = pontos_circuito[0].id
    solicitacao.ponto_destino_id = pontos_circuito[2].id
    buffer_fim = relogio.agora + timedelta(minutes=5)
    _abrir_buffer(_db, viagem_solicitada, buffer_fim)
    relogio.avancar(minutes=6)

    assert buffer_service.fechar_buffers_expirados() == 1

    viagem = _db.session.get(Viagem, viagem_solicitada.id)
    assert viagem.status == StatusViagem.EM_ANDAMENTO
    assert viagem.inicio_real == buffer_fim
    assert _notificacoes(motorista.user.id) == 1
    assert _notificacoes(aluno.user.id) == 1

    # RF-15: quem declarou vira passageiro com credencial e o roteiro é materializado.
    passageiro = _db.session.get(AlunosConfirmados, (viagem.id, aluno.user.id))
    assert passageiro.confirmacao is True
    assert passageiro.ponto_embarque_id == pontos_circuito[0].id
    assert CredencialEmbarque.query.filter_by(viagem_id=viagem.id).count() == 1
    assert len(viagem.pontos_visitados) == 4


def test_buffer_expirado_sem_trajeto_declarado_cancela_a_viagem(
    _db, viagem_solicitada, motorista, aluno, relogio
):
    """RF-15, fluxo secundário 1: sem trajeto aceito, o veículo volta a ficar ocioso."""
    _abrir_buffer(_db, viagem_solicitada, relogio.agora + timedelta(minutes=5))
    relogio.avancar(minutes=6)

    assert buffer_service.fechar_buffers_expirados() == 1

    viagem = _db.session.get(Viagem, viagem_solicitada.id)
    assert viagem.status == StatusViagem.CANCELADA
    assert viagem.inicio_real is None
    assert viagem.solicitacoes[0].status == StatusSolicitacao.CANCELADA
    assert AlunosConfirmados.query.filter_by(viagem_id=viagem.id).count() == 0
    assert _notificacoes(motorista.user.id) == 1
    assert _notificacoes(aluno.user.id) == 0


def test_buffer_nao_expirado_fica_intacto(_db, viagem_solicitada, relogio):
    _abrir_buffer(_db, viagem_solicitada, relogio.agora + timedelta(minutes=5))
    relogio.avancar(minutes=4)

    assert buffer_service.fechar_buffers_expirados() == 0

    viagem = _db.session.get(Viagem, viagem_solicitada.id)
    assert viagem.status == StatusViagem.BUFFER_ABERTO
    assert viagem.inicio_real is None


# --- Job: alerta de prazo de início ------------------------------------------


def test_prazo_alerta_gestor_uma_vez(_db, viagem_solicitada, gestor, other_gestor, relogio):
    relogio.avancar(minutes=10)

    assert buffer_service.alertar_prazo_inicio() == 1
    assert buffer_service.alertar_prazo_inicio() == 0

    assert _notificacoes(gestor.user.id) == 1
    assert _notificacoes(other_gestor.user.id) == 0
    assert _db.session.get(Viagem, viagem_solicitada.id).aviso_prazo_enviado is True


def test_prazo_nao_alerta_gestor_inativo(_db, viagem_solicitada, organizacao, relogio):
    inativo = GestorFactory(organizacao_id=organizacao.id, status=UserStatus.DISABLED)
    _db.session.add(inativo)
    _db.session.commit()
    relogio.avancar(minutes=10)

    buffer_service.alertar_prazo_inicio()

    assert _notificacoes(inativo.id) == 0


def test_prazo_nao_alerta_antes_do_prazo(_db, viagem_solicitada, gestor, relogio):
    relogio.avancar(minutes=9)

    assert buffer_service.alertar_prazo_inicio() == 0
    assert _notificacoes(gestor.user.id) == 0


def test_prazo_nao_alerta_viagem_ja_iniciada(_db, viagem_solicitada, gestor, relogio):
    _abrir_buffer(_db, viagem_solicitada, relogio.agora + timedelta(minutes=5))
    relogio.avancar(minutes=30)

    assert buffer_service.alertar_prazo_inicio() == 0
    assert _notificacoes(gestor.user.id) == 0


def _em_rota(_db, viagem, pontos, relogio):
    solicitacao = viagem.solicitacoes[0]
    solicitacao.ponto_embarque_id = pontos[0].id
    solicitacao.ponto_destino_id = pontos[2].id
    _abrir_buffer(_db, viagem, relogio.agora + timedelta(minutes=5))
    relogio.avancar(minutes=6)
    buffer_service.fechar_buffers_expirados()


def test_motorista_de_viagem_sob_demanda_em_rota_fica_em_rota(
    _db, viagem_solicitada, circuito, pontos_circuito, motorista, relogio
):
    """PR #16 calcula o estado do motorista pela viagem EM_ANDAMENTO, também a sob demanda."""
    _em_rota(_db, viagem_solicitada, pontos_circuito, relogio)

    estado = viagens_service.status_motorista(motorista.user, relogio.agora)
    assert estado == StatusMotorista.EM_ROTA


def test_gestor_cancelar_viagem_sob_demanda_iniciada_fecha_fim_real(
    _db, viagem_solicitada, circuito, pontos_circuito, gestor, relogio
):
    _em_rota(_db, viagem_solicitada, pontos_circuito, relogio)

    r = gestor.client.put(f"/v1/viagens/{viagem_solicitada.id}/cancelar")

    assert r.status_code == 200, r.get_data(as_text=True)
    viagem = _db.session.get(Viagem, viagem_solicitada.id)
    assert viagem.status == StatusViagem.CANCELADA
    assert viagem.fim_real == relogio.agora
