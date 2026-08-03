"""Background tasks for trip management, including automated geofence-based check-ins."""

import logging
from datetime import UTC, datetime, timedelta

from app.extensions import scheduler
from app.models.base import db
from app.models.enum import StatusSolicitacao, StatusViagem
from app.models.viagem import AlunosConfirmados, Viagem
from app.services.notificacao_service import NotificacaoService
from app.utils.geo_utils import calcular_distancia_metros

logger = logging.getLogger(__name__)

BUFFER_MINUTOS_PADRAO = 5


def consolidar_buffers_expirados() -> int:
    """RF-15: buffer vencido para de aceitar declarações e consolida a rodada.

    Com pelo menos um embarque aceito a rodada vira *Em rota*; sem nenhum ela
    volta a *Ociosa* e o motorista é avisado de que a rodada foi cancelada
    (fluxo secundário 1). Precisa de um app context ativo.
    """
    agora = datetime.now(UTC)
    viagens = Viagem.query.filter(
        Viagem.status == StatusViagem.BUFFER_ABERTO,
        Viagem.buffer_expira_em.isnot(None),
        Viagem.buffer_expira_em <= agora,
    ).all()

    for viagem in viagens:
        confirmados = [
            c for c in viagem.alunos_confirmados if c.status == StatusSolicitacao.CONFIRMADO
        ]

        # Quem só demonstrou interesse e não declarou trajeto sai da rodada:
        # a linha continua no histórico, mas não pesa na próxima rodada, que
        # reaproveita a mesma viagem quando ela volta a ficar ociosa.
        for participante in viagem.alunos_confirmados:
            if participante.status == StatusSolicitacao.INTERESSADO:
                participante.status = StatusSolicitacao.CANCELADO

        viagem.buffer_expira_em = None

        if confirmados:
            viagem.status = StatusViagem.EM_ROTA
            viagem.inicio_real = agora
            # Emissão das credenciais QR (RF-15) é do plano de embarque: ela
            # entra aqui, sobre esta mesma lista de confirmados.
            NotificacaoService.notificar_rodada_consolidada(
                viagem, [c.aluno_id for c in confirmados]
            )
        else:
            viagem.status = StatusViagem.OCIOSA
            NotificacaoService.notificar_rodada_cancelada(viagem)

    if viagens:
        db.session.commit()

    return len(viagens)


def cobrar_demandas_nao_atendidas() -> int:
    """RF-11 fluxo secundário 1: motorista não iniciou dentro do prazo
    operacional, então o gestor é chamado para tratar a demanda à mão.

    O prazo é o mesmo N do buffer configurado na janela — é o único parâmetro
    de tempo que o gestor define por janela.
    """
    agora = datetime.now(UTC)
    avisadas = 0

    viagens = Viagem.query.filter(
        Viagem.status == StatusViagem.SOLICITADA,
        Viagem.rota_id.isnot(None),
        # ponytail: reaproveita a flag do fluxo programado como "gestor já
        # avisado desta rodada". Uma coluna própria seria mais clara, mas o
        # esquema está fechado; renomear é migração, não código.
        Viagem.aviso_10min_enviado.is_(False),
    ).all()

    for viagem in viagens:
        solicitacoes = [c.solicitado_em for c in viagem.alunos_confirmados if c.solicitado_em]
        if not solicitacoes:
            continue

        minutos = viagem.janela.buffer_minutos if viagem.janela else BUFFER_MINUTOS_PADRAO
        if agora - min(solicitacoes) < timedelta(minutes=minutos):
            continue

        NotificacaoService.notificar_gestor_demanda_nao_atendida(viagem)
        viagem.aviso_10min_enviado = True
        avisadas += 1

    if avisadas:
        db.session.commit()

    return avisadas


def processar_rodadas(app) -> None:
    """Job periódico das rodadas sob demanda.

    Uma varredura periódica em vez de um job agendado por viagem: o job por
    viagem se perde quando o processo do scheduler reinicia, e uma rodada
    presa em BUFFER_ABERTO nunca mais sairia de lá.
    """
    with app.app_context():
        try:
            consolidar_buffers_expirados()
            cobrar_demandas_nao_atendidas()
        except Exception as e:
            db.session.rollback()
            logger.error(f"Erro ao processar rodadas sob demanda: {e}")


def realizar_auto_checkin(viagem_id: str, aluno_id: str, tentativa: int) -> None:
    """
    Verifica o embarque do aluno comparando GPS.
    """
    if tentativa > 3:
        logger.warning(
            f"Auto-checkin abortado: Limite de tentativas excedido para o aluno {aluno_id}"
        )
        return

    app = scheduler.app

    if not app:
        logger.error("Erro fatal: Instância do Flask (app) não encontrada no Scheduler.")
        return

    with app.app_context():
        conf = AlunosConfirmados.query.filter_by(viagem_id=viagem_id, aluno_id=aluno_id).first()
        viagem = db.session.get(Viagem, viagem_id)

        if not conf or not viagem or conf.embarcou:
            return

        agora = datetime.now(UTC)
        DISTANCIA_EMBARQUE = 50

        if conf.aluno_lat and viagem.motorista_lat:
            distancia = calcular_distancia_metros(
                viagem.motorista_lat, viagem.motorista_lon, conf.aluno_lat, conf.aluno_lon
            )

            if distancia <= DISTANCIA_EMBARQUE:
                conf.embarcou = True
                db.session.commit()

                NotificacaoService._criar_notificacao_interna(
                    usuario_id=aluno_id,
                    titulo="✅ Embarque Confirmado!",
                    mensagem="Detectamos você no ônibus. Boa viagem!",
                )
                return

        if tentativa < 3:
            conf.tentativas_auto_checkin = tentativa
            db.session.commit()

            nova_data = agora + timedelta(minutes=5)
            job_id = f"checkin_{viagem_id}_{aluno_id}_{tentativa+1}"

            scheduler.add_job(
                id=job_id,
                func=realizar_auto_checkin,
                args=[viagem_id, aluno_id, tentativa + 1],
                trigger="date",
                run_date=nova_data,
            )
