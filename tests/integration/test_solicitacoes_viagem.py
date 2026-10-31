"""Solicitação de viagem sob demanda (RF-10) e cancelamento (RF-19), pela API HTTP."""

from datetime import UTC, datetime, time

import pytest
from flask_jwt_extended import create_access_token

from app.models.consentimento import ACEITE, REVOGACAO, Consentimento
from app.models.enum import DiaDaSemana, StatusSolicitacao, StatusViagem, TipoViagem
from app.models.notificacao import Notificacao
from app.models.viagem import SolicitacaoViagem, Viagem
from app.services.consentimento_service import VERSAO_TERMO_VIGENTE
from tests.conftest import Actor, AuthenticatedClient
from tests.factories.onibus_factory import JanelaDisponibilidadeFactory
from tests.factories.rota_factory import RotaFactory
from tests.factories.user_factory import AlunoFactory
from tests.factories.viagem_factory import SolicitacaoViagemFactory, ViagemFactory


@pytest.fixture()
def segundo_aluno(client, app, _db, organizacao):
    u = AlunoFactory(organizacao_id=organizacao.id)
    _db.session.add(u)
    _db.session.commit()
    _db.session.add(Consentimento(usuario_id=u.id, versao=VERSAO_TERMO_VIGENTE, acao=ACEITE))
    _db.session.commit()
    with app.app_context():
        token = create_access_token(identity=str(u.id))
    headers = {"Authorization": f"Bearer {token}"}
    return Actor(user=u, headers=headers, client=AuthenticatedClient(client, headers))


def _solicitar(actor, rota):
    return actor.client.post(f"/v1/rotas/{rota.id}/solicitacoes")


def _cancelar(actor, viagem_id):
    return actor.client.delete(f"/v1/viagens/{viagem_id}/solicitacao")


def _notificacoes(usuario_id):
    return Notificacao.query.filter_by(usuario_id=usuario_id).count()


def _local(hora, minuto=0):
    # Segunda 2026-11-02 em Fortaleza (UTC-3).
    return datetime(2026, 11, 2, hora + 3, minuto, tzinfo=UTC)


# RF-10: janela de disponibilidade


def test_antes_da_janela_rejeita_listando_horarios(_db, aluno, rota_sob_demanda, janela, relogio):
    _db.session.add(
        JanelaDisponibilidadeFactory(
            onibus_id=janela.onibus_id,
            motorista_id=janela.motorista_id,
            dia=DiaDaSemana.SEG,
            hora_inicio=time(14, 0),
            hora_fim=time(18, 0),
        )
    )
    _db.session.commit()
    relogio.ajustar(_local(7, 30))

    r = _solicitar(aluno, rota_sob_demanda)

    assert r.status_code == 400
    assert r.get_json()["error"]["message"] == (
        "Fora da janela de disponibilidade. Horários de hoje: 08:00–12:00, 14:00–18:00."
    )
    assert SolicitacaoViagem.query.count() == 0


def test_depois_da_janela_rejeita(aluno, rota_sob_demanda, janela, relogio):
    relogio.ajustar(_local(13))

    r = _solicitar(aluno, rota_sob_demanda)

    assert r.status_code == 400
    assert "08:00–12:00" in r.get_json()["error"]["message"]


def test_sem_janela_no_dia_rejeita(aluno, rota_sob_demanda, janela, relogio):
    relogio.ajustar(datetime(2026, 11, 3, 13, 0, tzinfo=UTC))  # terça 10:00

    r = _solicitar(aluno, rota_sob_demanda)

    assert r.status_code == 400
    assert "Não há operação hoje" in r.get_json()["error"]["message"]


def test_exatamente_no_inicio_da_janela_aceita(aluno, rota_sob_demanda, janela, relogio):
    relogio.ajustar(_local(8))

    r = _solicitar(aluno, rota_sob_demanda)

    assert r.status_code == 201, r.get_data(as_text=True)


def test_exatamente_no_fim_da_janela_rejeita(aluno, rota_sob_demanda, janela, relogio):
    relogio.ajustar(_local(12))

    r = _solicitar(aluno, rota_sob_demanda)

    assert r.status_code == 400


# RF-10: validações da rota e do usuário


def test_rota_fixa_rejeita(aluno, rota, janela, relogio):
    r = _solicitar(aluno, rota)

    assert r.status_code == 400
    assert "horário fixo" in r.get_json()["error"]["message"]


def test_rota_sem_veiculo_rejeita(_db, aluno, organizacao, janela, relogio):
    sem_veiculo = RotaFactory(
        organizacao_id=organizacao.id,
        tipo=TipoViagem.SOB_DEMANDA,
        buffer_minutos=5,
        prazo_inicio_minutos=10,
        motorista_padrao_id=None,
        veiculo_padrao_id=None,
    )
    _db.session.add(sem_veiculo)
    _db.session.commit()

    r = _solicitar(aluno, sem_veiculo)

    assert r.status_code == 400
    assert "veículo" in r.get_json()["error"]["message"]


def test_rota_de_outra_organizacao_rejeita(other_aluno, rota_sob_demanda, janela, relogio):
    r = _solicitar(other_aluno, rota_sob_demanda)

    assert r.status_code == 403


def test_rota_inexistente_retorna_404(aluno, relogio):
    r = aluno.client.post("/v1/rotas/00000000-0000-0000-0000-000000000000/solicitacoes")

    assert r.status_code == 404


def test_nao_aluno_rejeita(gestor, rota_sob_demanda, janela, relogio):
    r = _solicitar(gestor, rota_sob_demanda)

    assert r.status_code == 403


def test_sem_consentimento_rejeita(_db, aluno, rota_sob_demanda, janela, relogio):
    _db.session.add(
        Consentimento(usuario_id=aluno.user.id, versao=VERSAO_TERMO_VIGENTE, acao=REVOGACAO)
    )
    _db.session.commit()

    r = _solicitar(aluno, rota_sob_demanda)

    assert r.status_code == 403
    assert SolicitacaoViagem.query.count() == 0


# RF-10: rodada


def test_primeira_solicitacao_cria_viagem_e_notifica_motorista(
    _db, aluno, motorista, rota_sob_demanda, janela, relogio
):
    r = _solicitar(aluno, rota_sob_demanda)

    assert r.status_code == 201, r.get_data(as_text=True)
    body = r.get_json()
    assert body["status"] == "ATIVA"
    assert body["viagem"]["status"] == "SOLICITADA"
    assert body["viagem"]["rota_id"] == str(rota_sob_demanda.id)
    assert body["viagem"]["motorista_id"] == str(motorista.user.id)
    assert body["viagem"]["buffer_fim"] is None

    viagem = _db.session.get(Viagem, body["viagem_id"])
    assert viagem.horario_rota_id is None
    assert viagem.veiculo_id == rota_sob_demanda.veiculo_padrao_id
    assert viagem.data == _local(10).date()
    assert _notificacoes(motorista.user.id) == 1


def test_segundo_aluno_entra_na_mesma_viagem_sem_nova_notificacao(
    aluno, segundo_aluno, motorista, rota_sob_demanda, janela, relogio
):
    primeira = _solicitar(aluno, rota_sob_demanda).get_json()

    r = _solicitar(segundo_aluno, rota_sob_demanda)

    assert r.status_code == 201, r.get_data(as_text=True)
    assert r.get_json()["viagem_id"] == primeira["viagem_id"]
    assert Viagem.query.count() == 1
    assert _notificacoes(motorista.user.id) == 1


def test_entra_com_buffer_aberto(
    _db, segundo_aluno, motorista, viagem_solicitada, rota_sob_demanda, janela, relogio
):
    viagem_solicitada.status = StatusViagem.BUFFER_ABERTO
    _db.session.commit()

    r = _solicitar(segundo_aluno, rota_sob_demanda)

    assert r.status_code == 201, r.get_data(as_text=True)
    assert r.get_json()["viagem_id"] == str(viagem_solicitada.id)
    assert r.get_json()["viagem"]["status"] == "BUFFER_ABERTO"
    assert _notificacoes(motorista.user.id) == 0


def test_mesmo_aluno_duas_vezes_conflita(aluno, rota_sob_demanda, janela, relogio):
    assert _solicitar(aluno, rota_sob_demanda).status_code == 201

    r = _solicitar(aluno, rota_sob_demanda)

    assert r.status_code == 409
    assert SolicitacaoViagem.query.count() == 1


def test_veiculo_em_rota_conflita(
    _db, segundo_aluno, viagem_solicitada, rota_sob_demanda, janela, relogio
):
    viagem_solicitada.status = StatusViagem.EM_ANDAMENTO
    _db.session.commit()

    r = _solicitar(segundo_aluno, rota_sob_demanda)

    assert r.status_code == 409


def test_veiculo_atendendo_outra_rota_conflita(
    _db, aluno, organizacao, onibus, rota_sob_demanda, janela, relogio
):
    outra = RotaFactory(
        organizacao_id=organizacao.id,
        tipo=TipoViagem.SOB_DEMANDA,
        buffer_minutos=5,
        prazo_inicio_minutos=10,
        motorista_padrao_id=None,
        veiculo_padrao_id=onibus.id,
    )
    _db.session.add(outra)
    _db.session.flush()
    _db.session.add(
        ViagemFactory(
            rota_id=outra.id,
            data=_local(10).date(),
            status=StatusViagem.SOLICITADA,
            veiculo_id=onibus.id,
        )
    )
    _db.session.commit()

    r = _solicitar(aluno, rota_sob_demanda)

    assert r.status_code == 409


# RF-19: cancelamento


def test_cancela_em_solicitada_com_outro_interessado_mantem_viagem(
    _db, aluno, segundo_aluno, motorista, viagem_solicitada, relogio
):
    _db.session.add(
        SolicitacaoViagemFactory(viagem_id=viagem_solicitada.id, aluno_id=segundo_aluno.user.id)
    )
    _db.session.commit()

    r = _cancelar(aluno, viagem_solicitada.id)

    assert r.status_code == 200, r.get_data(as_text=True)
    assert r.get_json()["status"] == "CANCELADA"
    assert r.get_json()["viagem"]["status"] == "SOLICITADA"
    assert _notificacoes(motorista.user.id) == 0


def test_cancela_ultima_solicitacao_cancela_viagem_e_notifica(
    _db, aluno, motorista, viagem_solicitada, relogio
):
    r = _cancelar(aluno, viagem_solicitada.id)

    assert r.status_code == 200, r.get_data(as_text=True)
    assert r.get_json()["viagem"]["status"] == "CANCELADA"
    solicitacao = SolicitacaoViagem.query.filter_by(viagem_id=viagem_solicitada.id).one()
    assert solicitacao.status == StatusSolicitacao.CANCELADA
    assert solicitacao.cancelada_em == relogio.agora
    assert _notificacoes(motorista.user.id) == 1


def test_cancela_com_buffer_aberto_mantem_viagem(_db, aluno, motorista, viagem_solicitada, relogio):
    viagem_solicitada.status = StatusViagem.BUFFER_ABERTO
    _db.session.commit()

    r = _cancelar(aluno, viagem_solicitada.id)

    assert r.status_code == 200, r.get_data(as_text=True)
    assert r.get_json()["status"] == "CANCELADA"
    assert r.get_json()["viagem"]["status"] == "BUFFER_ABERTO"
    assert _notificacoes(motorista.user.id) == 0


def test_cancela_depois_do_inicio_vira_desistencia(
    _db, aluno, motorista, viagem_solicitada, relogio
):
    viagem_solicitada.status = StatusViagem.EM_ANDAMENTO
    _db.session.commit()

    r = _cancelar(aluno, viagem_solicitada.id)

    assert r.status_code == 200, r.get_data(as_text=True)
    assert r.get_json()["status"] == "DESISTENCIA"
    assert r.get_json()["viagem"]["status"] == "EM_ANDAMENTO"
    assert _notificacoes(motorista.user.id) == 1


def test_cancela_duas_vezes_retorna_404(aluno, viagem_solicitada, relogio):
    assert _cancelar(aluno, viagem_solicitada.id).status_code == 200

    r = _cancelar(aluno, viagem_solicitada.id)

    assert r.status_code == 404


def test_aluno_sem_solicitacao_na_viagem_retorna_404(segundo_aluno, viagem_solicitada, relogio):
    r = _cancelar(segundo_aluno, viagem_solicitada.id)

    assert r.status_code == 404
    assert SolicitacaoViagem.query.filter_by(status=StatusSolicitacao.ATIVA).count() == 1


def test_cancela_viagem_finalizada_rejeita(_db, aluno, viagem_solicitada, relogio):
    viagem_solicitada.status = StatusViagem.FINALIZADA
    _db.session.commit()

    r = _cancelar(aluno, viagem_solicitada.id)

    assert r.status_code == 400


def test_cancela_sem_consentimento_funciona(_db, aluno, viagem_solicitada, relogio):
    _db.session.add(
        Consentimento(usuario_id=aluno.user.id, versao=VERSAO_TERMO_VIGENTE, acao=REVOGACAO)
    )
    _db.session.commit()

    r = _cancelar(aluno, viagem_solicitada.id)

    assert r.status_code == 200, r.get_data(as_text=True)
