"""Janela de buffer das viagens sob demanda (RF-11, RF-12) e jobs que a fecham."""

import logging
import math
from datetime import datetime, timedelta

from app.core.exceptions import ConflictError, ForbiddenError, NotFoundError
from app.models.base import db
from app.models.enum import StatusSolicitacao, StatusViagem, UserRole, UserStatus
from app.models.user import Aluno, Gestor, User
from app.models.viagem import AlunosConfirmados, SolicitacaoViagem, Viagem
from app.services import consentimento_service, embarque_service
from app.services.notificacao_service import NotificacaoService
from app.utils import tempo
from app.utils.validators import validate_uuid

logger = logging.getLogger(__name__)


def iniciar_percurso(user_id: str, viagem_id: str) -> Viagem:
    """RF-11: o motorista da viagem abre a janela de buffer."""
    # Trava a linha: dois toques no botão não podem abrir o buffer duas vezes.
    # NO KEY: a solicitação que entra na rodada só precisa da chave da viagem (FK).
    viagem = (
        db.session.query(Viagem)
        .filter(Viagem.id == validate_uuid(viagem_id, "ID da viagem"))
        .with_for_update(key_share=True)
        .first()
    )
    if not viagem:
        raise NotFoundError("Viagem não encontrada")

    user = db.session.get(User, user_id)
    if not user or user.role != UserRole.MOTORISTA or viagem.motorista_id != user.id:
        db.session.rollback()
        raise ForbiddenError("Apenas o motorista da viagem pode iniciar o percurso")

    if viagem.status != StatusViagem.SOLICITADA:
        db.session.rollback()
        raise ConflictError(f"A viagem não pode iniciar o percurso no status {viagem.status.value}")

    # shortcut: once PR #16 merges, call _validar_jornada_motorista(motorista, agora) here (409 when
    # status_motorista(...) is EM_ROTA, 403 on rest/hours) and clear descanso_ate. EM_ROTA itself is
    # computed from the trip being EM_ANDAMENTO, so nothing else is stored.
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


# shortcut: PR #16 needs nothing new here: the driver was validated in iniciar_percurso, and
# EM_ANDAMENTO plus inicio_real below are what its computed state and rest calculation read.
def colocar_em_rota(viagem: Viagem, momento: datetime, declaradas: list[SolicitacaoViagem]) -> None:
    """Única transição sob demanda para EM_ANDAMENTO; inicio_real conta o tempo de direção.

    Fecha a rodada (RF-15): cada trajeto aceito vira passageiro com credencial de embarque.
    """
    viagem.status = StatusViagem.EM_ANDAMENTO
    viagem.inicio_real = momento

    passageiros = []
    for solicitacao in declaradas:
        passageiro = AlunosConfirmados(
            viagem_id=viagem.id,
            aluno_id=solicitacao.aluno_id,
            confirmacao=True,
            ponto_embarque_id=solicitacao.ponto_embarque_id,
            ponto_destino_id=solicitacao.ponto_destino_id,
        )
        db.session.add(passageiro)
        passageiros.append(passageiro)
    db.session.flush()

    embarque_service.consolidar_embarque(viagem, passageiros)


def fechar_buffers_expirados() -> int:
    """Job: buffer expirado vira EM_ANDAMENTO com quem declarou trajeto; sem ninguém, é cancelada."""
    agora = tempo.agora_utc()
    # Trava as viagens: uma declaração ou um cancelamento em curso termina antes do
    # fechamento ler as solicitações. A ordem por id evita deadlock entre dois jobs.
    viagens = (
        Viagem.query.filter(
            Viagem.status == StatusViagem.BUFFER_ABERTO,
            Viagem.buffer_fim <= agora,
        )
        .order_by(Viagem.id)
        .with_for_update(key_share=True)
        .populate_existing()
        .all()
    )

    for viagem in viagens:
        # O instante em que o buffer fechou de fato, não o atraso do job.
        fim = viagem.buffer_fim

        declaradas = []
        for solicitacao in viagem.solicitacoes:
            if solicitacao.status != StatusSolicitacao.ATIVA:
                continue
            if solicitacao.ponto_embarque_id is None:
                # Só demonstrou interesse e não declarou trajeto: sai da rodada.
                solicitacao.status = StatusSolicitacao.CANCELADA
                solicitacao.cancelada_em = fim
            else:
                declaradas.append(solicitacao)

        if not declaradas:
            # RF-15, fluxo secundário 1: nenhum trajeto aceito, o veículo volta a ficar ocioso.
            viagem.status = StatusViagem.CANCELADA
            NotificacaoService._criar_notificacao_interna(
                usuario_id=viagem.motorista_id,
                titulo="Viagem cancelada",
                mensagem="O buffer terminou sem trajetos declarados. O veículo volta a ficar ocioso.",
            )
            continue

        colocar_em_rota(viagem, fim, declaradas)

        NotificacaoService._criar_notificacao_interna(
            usuario_id=viagem.motorista_id,
            titulo="🚐 Buffer encerrado",
            mensagem="A janela de buffer terminou. Pode seguir com o percurso.",
        )

        for solicitacao in declaradas:
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
