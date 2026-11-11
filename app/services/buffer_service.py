"""Buffer window of on-demand trips (RF-11, RF-12) and the jobs that close it."""

import logging
import math
from datetime import datetime, timedelta

from app.core.exceptions import ConflictError, ForbiddenError, NotFoundError
from app.models.base import db
from app.models.enum import StatusSolicitacao, StatusViagem, UserRole, UserStatus
from app.models.user import Aluno, Gestor, Motorista, User
from app.models.viagem import AlunosConfirmados, SolicitacaoViagem, Viagem
from app.services import (
    consentimento_service,
    embarque_service,
    parametros_operacao_service,
    viagens_service,
)
from app.services.notificacao_service import NotificacaoService
from app.utils import tempo
from app.utils.validators import validate_uuid

logger = logging.getLogger(__name__)


def iniciar_percurso(user_id: str, viagem_id: str) -> Viagem:
    """RF-11: the trip's driver opens the buffer window."""
    # Lock the row: two taps on the button must not open the buffer twice.
    # NO KEY: a request joining the round only needs the trip's key (FK).
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

    parametros = parametros_operacao_service.parametros_da_organizacao(viagem.rota.organizacao_id)
    _exigir_minimo_alunos(viagem, parametros.minimo_alunos)

    # Same lock order as controlar_viagem (trip, then driver).
    motorista = (
        db.session.query(Motorista)
        .filter(Motorista.id == viagem.motorista_id)
        .with_for_update(of=Motorista)
        .populate_existing()
        .one()
    )
    try:
        # 409 while on another trip, 403 during rest/pause or outside working hours.
        viagens_service._validar_jornada_motorista(motorista, tempo.agora_utc())
    except Exception:
        db.session.rollback()
        raise
    motorista.descanso_ate = None
    viagem.status = StatusViagem.BUFFER_ABERTO
    viagem.buffer_fim = tempo.agora_utc() + timedelta(minutes=viagem.rota.buffer_minutos)
    db.session.commit()

    notificar_abertura_buffer(viagem)
    return viagem


def _exigir_minimo_alunos(viagem: Viagem, minimo: int) -> None:
    solicitantes = (
        db.session.query(SolicitacaoViagem.id)
        .filter_by(viagem_id=viagem.id, status=StatusSolicitacao.ATIVA)
        .count()
    )
    if solicitantes < minimo:
        db.session.rollback()
        raise ConflictError(
            f"A viagem precisa de pelo menos {minimo} aluno(s) solicitante(s) para iniciar "
            f"o percurso (atual: {solicitantes})"
        )


def notificar_abertura_buffer(viagem: Viagem) -> None:
    """RF-12: notifies all eligible students in the route's organization."""
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
    """The only on-demand transition to EM_ANDAMENTO; inicio_real counts driving time.

    Closes the round (RF-15): each accepted route becomes a passenger with a boarding credential.
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
    """Job: an expired buffer goes EM_ANDAMENTO with whoever declared; if none, it is cancelled."""
    agora = tempo.agora_utc()
    # Lock the trips: an in-flight declaration or cancellation finishes before the
    # close reads the requests. Ordering by id avoids deadlock between two jobs.
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
        # The moment the buffer actually closed, not the job's delay.
        fim = viagem.buffer_fim

        declaradas = []
        for solicitacao in viagem.solicitacoes:
            if solicitacao.status != StatusSolicitacao.ATIVA:
                continue
            if solicitacao.ponto_embarque_id is None:
                # Only showed interest and did not declare a route: leaves the round.
                solicitacao.status = StatusSolicitacao.CANCELADA
                solicitacao.cancelada_em = fim
            else:
                declaradas.append(solicitacao)

        if not declaradas:
            # RF-15, secondary flow 1: no route accepted, the vehicle goes back to idle.
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
    """Job (RF-11, secondary flow): alerts the manager when the driver does not start on time."""
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
