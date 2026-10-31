"""Expiração do buffer (RF-15) e cobrança da demanda parada (RF-11 fluxo 1).

Uma varredura periódica cuida das duas coisas, então os testes chamam as
funções da varredura direto — o scheduler nunca roda na suíte.
"""

from datetime import UTC, datetime, timedelta

import pytest

from app.models.enum import StatusSolicitacao, StatusViagem
from app.models.notificacao import Notificacao
from app.models.viagem import AlunosConfirmados
from app.services import capacidade_service
from app.tasks.viagem_tasks import cobrar_demandas_nao_atendidas, consolidar_buffers_expirados


@pytest.fixture()
def buffer_vencido(_db, viagem_ociosa):
    viagem_ociosa.status = StatusViagem.BUFFER_ABERTO
    viagem_ociosa.buffer_expira_em = datetime.now(UTC) - timedelta(seconds=1)
    _db.session.commit()
    return viagem_ociosa


def _notificacoes(_db, usuario_id):
    return _db.session.query(Notificacao).filter_by(usuario_id=usuario_id).all()


@pytest.mark.integration
def test_buffer_vencido_sem_embarque_volta_para_ociosa_e_avisa_o_motorista(
    _db, buffer_vencido, aluno, motorista
):
    """RF-15 fluxo secundário 1."""
    _db.session.add(
        AlunosConfirmados(
            viagem_id=buffer_vencido.id,
            aluno_id=aluno.user.id,
            confirmacao=False,
            status=StatusSolicitacao.INTERESSADO,
        )
    )
    _db.session.commit()

    assert consolidar_buffers_expirados() == 1

    _db.session.refresh(buffer_vencido)
    assert buffer_vencido.status == StatusViagem.OCIOSA
    assert buffer_vencido.buffer_expira_em is None
    assert buffer_vencido.inicio_real is None

    # O interessado que não declarou trajeto sai da rodada.
    registro = _db.session.get(AlunosConfirmados, (buffer_vencido.id, aluno.user.id))
    assert registro.status == StatusSolicitacao.CANCELADO

    assert any("cancelada" in n.titulo.lower() for n in _notificacoes(_db, motorista.user.id))


@pytest.mark.integration
def test_buffer_vencido_com_embarque_confirmado_poe_a_rodada_em_rota(
    _db, buffer_vencido, aluno, motorista, pontos_circuito
):
    p1, p2, _, _ = pontos_circuito
    buffer_vencido.buffer_expira_em = datetime.now(UTC) + timedelta(minutes=5)
    _db.session.commit()

    capacidade_service.validar_e_reservar(buffer_vencido.id, aluno.user.id, p1.id, p2.id)

    buffer_vencido.buffer_expira_em = datetime.now(UTC) - timedelta(seconds=1)
    _db.session.commit()

    assert consolidar_buffers_expirados() == 1

    _db.session.refresh(buffer_vencido)
    assert buffer_vencido.status == StatusViagem.EM_ROTA
    assert buffer_vencido.buffer_expira_em is None
    assert buffer_vencido.inicio_real is not None

    registro = _db.session.get(AlunosConfirmados, (buffer_vencido.id, aluno.user.id))
    assert registro.status == StatusSolicitacao.CONFIRMADO

    assert _notificacoes(_db, aluno.user.id)
    assert _notificacoes(_db, motorista.user.id)


@pytest.mark.integration
def test_buffer_ainda_valido_nao_e_consolidado(_db, viagem_ociosa):
    viagem_ociosa.status = StatusViagem.BUFFER_ABERTO
    viagem_ociosa.buffer_expira_em = datetime.now(UTC) + timedelta(minutes=5)
    _db.session.commit()

    assert consolidar_buffers_expirados() == 0

    _db.session.refresh(viagem_ociosa)
    assert viagem_ociosa.status == StatusViagem.BUFFER_ABERTO


@pytest.mark.integration
def test_motorista_parado_alem_do_prazo_aciona_o_gestor(
    _db, viagem_ociosa, aluno, gestor, janela_hoje
):
    """RF-11 fluxo secundário 1."""
    viagem_ociosa.status = StatusViagem.SOLICITADA
    _db.session.add(
        AlunosConfirmados(
            viagem_id=viagem_ociosa.id,
            aluno_id=aluno.user.id,
            confirmacao=False,
            status=StatusSolicitacao.INTERESSADO,
            solicitado_em=datetime.now(UTC) - timedelta(minutes=janela_hoje.buffer_minutos + 1),
        )
    )
    _db.session.commit()

    assert cobrar_demandas_nao_atendidas() == 1
    assert any("demanda" in n.titulo.lower() for n in _notificacoes(_db, gestor.user.id))

    # Aviso único: a segunda varredura não repete a cobrança.
    assert cobrar_demandas_nao_atendidas() == 0
    assert len(_notificacoes(_db, gestor.user.id)) == 1


@pytest.mark.integration
def test_demanda_dentro_do_prazo_nao_aciona_o_gestor(_db, viagem_ociosa, aluno, gestor):
    viagem_ociosa.status = StatusViagem.SOLICITADA
    _db.session.add(
        AlunosConfirmados(
            viagem_id=viagem_ociosa.id,
            aluno_id=aluno.user.id,
            confirmacao=False,
            status=StatusSolicitacao.INTERESSADO,
            solicitado_em=datetime.now(UTC),
        )
    )
    _db.session.commit()

    assert cobrar_demandas_nao_atendidas() == 0
    assert _notificacoes(_db, gestor.user.id) == []


@pytest.mark.integration
def test_viagem_programada_nao_entra_na_varredura_da_rodada(
    _db, viagem_futura_agendada_com_motorista
):
    """A varredura é só das rodadas sob demanda; a viagem programada é intocada."""
    assert consolidar_buffers_expirados() == 0
    assert cobrar_demandas_nao_atendidas() == 0

    _db.session.refresh(viagem_futura_agendada_com_motorista)
    assert viagem_futura_agendada_com_motorista.status == StatusViagem.AGENDADA
