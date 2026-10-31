"""Janela de buffer das viagens sob demanda (RF-11, RF-12) e jobs que a fecham."""

import logging
import math
from datetime import datetime, timedelta

from app.core.exceptions import ConflictError, ForbiddenError, NotFoundError
from app.models.base import db
from app.models.enum import StatusSolicitacao, StatusViagem, UserRole, UserStatus
from app.models.user import Aluno, Gestor, User
from app.models.viagem import SolicitacaoViagem, Viagem
from app.services import consentimento_service
from app.services.notificacao_service import NotificacaoService
from app.utils import tempo

logger = logging.getLogger(__name__)


def iniciar_percurso(user_id: str, viagem_id: str) -> Viagem:
    """RF-11: o motorista da viagem abre a janela de buffer."""
    # Trava a linha: dois toques no botão não podem abrir o buffer duas vezes.
    viagem = db.session.query(Viagem).filter(Viagem.id == viagem_id).with_for_update().first()
    if not viagem:
        raise NotFoundError("Viagem não encontrada")

    user = db.session.get(User, user_id)
    if not user or user.role != UserRole.MOTORISTA or viagem.motorista_id != user.id:
        db.session.rollback()
        raise ForbiddenError("Apenas o motorista da viagem pode iniciar o percurso")

    if viagem.status != StatusViagem.SOLICITADA:
        db.session.rollback()
        raise ConflictError(f"A viagem não pode iniciar o percurso no status {viagem.status.value}")

    # shortcut: once PR #16 merges, call _validar_jornada_motorista(motorista, agora) here (403 on
    # rest/hours), 409 when motorista.status_atual(agora) is EM_ROTA, then set
    # status_motorista = EM_ROTA and descanso_ate = None: the driver is committed from this point.
    viagem.status = StatusViagem.BUFFER_ABERTO
    viagem.buffer_fim = tempo.agora_utc() + timedelta(minutes=viagem.rota.buffer_minutos)
    db.session.commit()

    notificar_abertura_buffer(viagem)
    return viagem


def notificar_abertura_buffer(viagem: Viagem) -> None:
    """RF-12: avisa todos os alunos aptos da organização da rota."""
    rota = viagem.rota
    restante = (viagem.buffer_fim - tempo.agora_utc()).total_seconds() / 60
    minutos = max(1, math.ceil(restante))

    alunos = Aluno.query.filter(
        Aluno.organizacao_id == rota.organizacao_id,
        Aluno.status == UserStatus.ACTIVE,
        Aluno.receber_notificacoes.is_(True),
    ).all()

    for aluno in alunos:
        # shortcut: uma consulta de consentimento por aluno, trocar por uma única consulta quando as organizações crescerem.
        if consentimento_service.consentimento_pendente(aluno.id):
            continue
        NotificacaoService._criar_notificacao_interna(
            usuario_id=aluno.id,
            titulo="🚐 Veículo saindo em instantes",
            mensagem=(
                f"A rota {rota.nome} vai iniciar o percurso. Você tem {minutos} minuto(s) "
                "para declarar sua origem e destino."
            ),
        )

    db.session.commit()


# shortcut: PR #16 needs nothing new here: the driver was validated and set EM_ROTA in
# iniciar_percurso; inicio_real below is what its rest calculation reads.
def colocar_em_rota(viagem: Viagem, momento: datetime) -> None:
    """Única transição sob demanda para EM_ANDAMENTO; inicio_real conta o tempo de direção."""
    viagem.status = StatusViagem.EM_ANDAMENTO
    viagem.inicio_real = momento


def fechar_buffers_expirados() -> int:
    """Job: buffer expirado vira EM_ANDAMENTO e avisa motorista e alunos da rodada."""
    agora = tempo.agora_utc()
    viagens = Viagem.query.filter(
        Viagem.status == StatusViagem.BUFFER_ABERTO,
        Viagem.buffer_fim <= agora,
    ).all()

    for viagem in viagens:
        # O instante em que o buffer fechou de fato, não o atraso do job.
        colocar_em_rota(viagem, viagem.buffer_fim)

        NotificacaoService._criar_notificacao_interna(
            usuario_id=viagem.motorista_id,
            titulo="🚐 Buffer encerrado",
            mensagem="A janela de buffer terminou. Pode seguir com o percurso.",
        )

        solicitacoes = SolicitacaoViagem.query.filter_by(
            viagem_id=viagem.id, status=StatusSolicitacao.ATIVA
        ).all()
        for solicitacao in solicitacoes:
            NotificacaoService._criar_notificacao_interna(
                usuario_id=solicitacao.aluno_id,
                titulo="🚐 Veículo em rota",
                mensagem=f"O veículo da rota {viagem.rota.nome} já está a caminho.",
            )

    try:
        db.session.commit()
    except Exception as e:
        db.session.rollback()
        logger.error(f"Erro no job de fechamento de buffer: {e}")
        return 0
    return len(viagens)


def alertar_prazo_inicio() -> int:
    """Job (RF-11, fluxo secundário): avisa o gestor quando o motorista não inicia no prazo."""
    agora = tempo.agora_utc()
    viagens = Viagem.query.filter(
        Viagem.status == StatusViagem.SOLICITADA,
        Viagem.aviso_prazo_enviado.is_(False),
    ).all()

    alertadas = 0
    for viagem in viagens:
        rota = viagem.rota
        if not rota or rota.prazo_inicio_minutos is None:
            continue
        prazo = viagem.created_at + timedelta(minutes=rota.prazo_inicio_minutos)
        if prazo > agora:
            continue

        gestores = Gestor.query.filter(
            Gestor.organizacao_id == rota.organizacao_id,
            Gestor.status == UserStatus.ACTIVE,
        ).all()
        for gestor in gestores:
            NotificacaoService._criar_notificacao_interna(
                usuario_id=gestor.id,
                titulo="⚠️ Percurso não iniciado",
                mensagem=(
                    f"O motorista da rota {rota.nome} não iniciou o percurso em "
                    f"{rota.prazo_inicio_minutos} minutos. Verifique a demanda."
                ),
            )
        viagem.aviso_prazo_enviado = True
        alertadas += 1

    try:
        db.session.commit()
    except Exception as e:
        db.session.rollback()
        logger.error(f"Erro no job de prazo de início: {e}")
        return 0
    return alertadas
