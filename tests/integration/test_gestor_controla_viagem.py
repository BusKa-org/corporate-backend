"""Gestor screen: cancel a trip with a reason and follow/control its progress."""

import pytest

from app.models.enum import StatusViagem
from app.models.notificacao import Notificacao


def _cancelar(gestor, viagem, corpo=None):
    return gestor.client.put(f"/v1/viagens/{viagem.id}/cancelar", json=corpo)


@pytest.mark.integration
def test_cancelar_com_motivo_avisa_alunos_e_motorista(
    gestor, aluno, motorista, confirmacao_aluno, viagem_futura_agendada_com_motorista, _db
):
    confirmacao_aluno.confirmacao = True
    _db.session.commit()

    r = _cancelar(gestor, viagem_futura_agendada_com_motorista, {"motivo": "Pneu furado"})
    assert r.status_code == 200, r.get_data(as_text=True)
    assert r.get_json()["alunos_notificados"] == 1

    aviso_aluno = Notificacao.query.filter_by(usuario_id=aluno.user.id).one()
    aviso_motorista = Notificacao.query.filter_by(usuario_id=motorista.user.id).one()
    assert "Motivo: Pneu furado" in aviso_aluno.mensagem
    assert "Motivo: Pneu furado" in aviso_motorista.mensagem
    _db.session.refresh(viagem_futura_agendada_com_motorista)
    assert viagem_futura_agendada_com_motorista.status == StatusViagem.CANCELADA


@pytest.mark.integration
def test_cancelar_sem_motivo_continua_valendo(
    gestor, motorista, viagem_futura_agendada_com_motorista
):
    r = _cancelar(gestor, viagem_futura_agendada_com_motorista)
    assert r.status_code == 200, r.get_data(as_text=True)
    aviso_motorista = Notificacao.query.filter_by(usuario_id=motorista.user.id).one()
    assert "Motivo" not in aviso_motorista.mensagem


@pytest.mark.integration
def test_motivo_longo_demais_e_recusado(gestor, viagem_futura_agendada_com_motorista, _db):
    r = _cancelar(gestor, viagem_futura_agendada_com_motorista, {"motivo": "x" * 256})
    assert r.status_code == 400, r.get_data(as_text=True)
    _db.session.refresh(viagem_futura_agendada_com_motorista)
    assert viagem_futura_agendada_com_motorista.status == StatusViagem.AGENDADA


@pytest.mark.integration
@pytest.mark.parametrize("status", [StatusViagem.FINALIZADA, StatusViagem.CANCELADA])
def test_cancelar_viagem_encerrada_responde_409(
    gestor, viagem_futura_agendada_com_motorista, status, _db
):
    viagem_futura_agendada_com_motorista.status = status
    _db.session.commit()

    r = _cancelar(gestor, viagem_futura_agendada_com_motorista)
    assert r.status_code == 409, r.get_data(as_text=True)


@pytest.mark.integration
def test_gestor_inicia_acompanha_e_finaliza(gestor, viagem_futura_agendada_com_motorista):
    viagem_id = viagem_futura_agendada_com_motorista.id

    r = gestor.client.put(f"/v1/viagens/{viagem_id}/acao", json={"acao": "INICIAR"})
    assert r.status_code == 200, r.get_data(as_text=True)

    assert gestor.client.get(f"/v1/viagens/{viagem_id}").get_json()["status"] == "EM_ANDAMENTO"
    progresso = gestor.client.get(f"/v1/dashboard/viagens/{viagem_id}/progresso")
    assert progresso.status_code == 200
    assert progresso.get_json() == []

    r = gestor.client.put(f"/v1/viagens/{viagem_id}/acao", json={"acao": "FINALIZAR"})
    assert r.status_code == 200, r.get_data(as_text=True)
    assert gestor.client.get(f"/v1/viagens/{viagem_id}").get_json()["status"] == "FINALIZADA"
