"""Notification service - management notifications for users."""

import logging
from datetime import UTC, datetime
from typing import Any

from firebase_admin import messaging
from sqlalchemy import event
from sqlalchemy.orm import Session, SessionTransaction

from app.core.exceptions import AppError, ForbiddenError, NotFoundError, ValidationError
from app.models.base import db
from app.models.enum import StatusSolicitacao, StatusViagem, UserRole, UserStatus
from app.models.notificacao import Notificacao
from app.models.rota import Rota, RotaAluno
from app.models.user import User
from app.models.viagem import AlunosConfirmados, SolicitacaoViagem, Viagem
from app.utils import audit_logger
from app.utils.validators import validate_uuid

logger = logging.getLogger(__name__)


PUSHES_PENDENTES = "pushes_pendentes"


def _enviar_push(fcm_token: str, usuario_id: str, titulo: str, mensagem: str) -> None:
    try:
        mensagem_fcm = messaging.Message(
            notification=messaging.Notification(
                title=titulo,
                body=mensagem,
            ),
            token=fcm_token,
        )
        response = messaging.send(mensagem_fcm)
        logger.info("Push enviado com sucesso para %s. ID: %s", usuario_id, response)

    except Exception:
        logger.exception("Falha ao enviar Push Notification via Firebase para %s", usuario_id)


@event.listens_for(Session, "after_commit")
def _enviar_pushes_pendentes(session: Session) -> None:
    pendentes = session.info.pop(PUSHES_PENDENTES, [])
    for fcm_token, usuario_id, titulo, mensagem in pendentes:
        _enviar_push(fcm_token, usuario_id, titulo, mensagem)


@event.listens_for(Session, "after_transaction_end")
def _descartar_pushes_pendentes(session: Session, transaction: SessionTransaction) -> None:
    # Rollback or close without commit; after a commit the list was already sent and popped.
    if transaction.parent is None:
        session.info.pop(PUSHES_PENDENTES, None)


class NotificacaoService:

    @staticmethod
    def _criar_notificacao_interna(usuario_id: str, titulo: str, mensagem: str) -> Notificacao:
        nova = Notificacao(
            usuario_id=usuario_id,
            titulo=titulo,
            mensagem=mensagem,
            data_envio=datetime.now(UTC),
        )
        db.session.add(nova)

        usuario = db.session.get(User, usuario_id)

        if usuario and getattr(usuario, "fcm_token", None):
            # Sent by _enviar_pushes_pendentes after commit, so a rollback sends nothing.
            pendentes = db.session.info.setdefault(PUSHES_PENDENTES, [])
            pendentes.append((usuario.fcm_token, str(usuario.id), titulo, mensagem))

        return nova

    @staticmethod
    def notificar_por_gestor(user_id: str, dados: dict[str, Any]) -> dict[str, Any]:
        user = db.session.get(User, user_id)
        if not user:
            raise ForbiddenError("Usuário não encontrado.")

        viagem_id = dados.get("viagem_id")

        # Motoristas can broadcast to their own active trip only
        if user.role == UserRole.MOTORISTA:
            if not viagem_id:
                raise ForbiddenError("Motoristas devem informar viagem_id para enviar avisos.")
            viagem = db.session.get(Viagem, validate_uuid(viagem_id, "viagem_id"))
            if not viagem or str(viagem.motorista_id) != str(user_id):
                raise ForbiddenError(
                    "Você só pode enviar avisos para viagens que você está conduzindo."
                )
            if viagem.status != StatusViagem.EM_ANDAMENTO:
                raise ForbiddenError("Você só pode enviar avisos durante uma viagem em andamento.")
        elif user.role != UserRole.GESTOR:
            raise ForbiddenError("Apenas gestores ou motoristas podem enviar comunicados.")

        destinatario_id = dados.get("destinatario_id")
        if destinatario_id and user.role != UserRole.GESTOR:
            raise ForbiddenError("Apenas gestores podem enviar avisos individuais.")

        titulo = dados.get("titulo")
        mensagem = dados.get("mensagem")
        rota_id = dados.get("rota_id")
        viagem_id = dados.get("viagem_id")

        if not titulo or not mensagem:
            raise ValidationError("Título e mensagem são obrigatórios.")

        # rota_id + viagem_id would let a motorista reach a whole route through its own trip.
        if (destinatario_id and (rota_id or viagem_id)) or (rota_id and viagem_id):
            raise ValidationError(
                "Informe apenas um destino: rota_id, viagem_id ou destinatario_id."
            )

        usuarios_notificados = set()

        if destinatario_id:
            destinatario = db.session.get(User, validate_uuid(destinatario_id, "destinatario_id"))
            # One 404 for missing, deleted or other-org users, so ids do not leak across tenants.
            if (
                not destinatario
                or destinatario.organizacao_id != user.organizacao_id
                or destinatario.status == UserStatus.DELETED
            ):
                raise NotFoundError("Usuário destinatário não encontrado.")
            usuarios_notificados.add(destinatario.id)
        elif rota_id:
            rota = db.session.get(Rota, validate_uuid(rota_id, "rota_id"))
            if not rota or rota.organizacao_id != user.organizacao_id:
                raise NotFoundError("Rota não encontrada.")
            # Inherited scheduled flow: a *route*'s audience is its subscriber list. The
            # on-demand round has no permanent subscription; its audience is the round's,
            # addressed by viagem_id below.
            inscricoes = RotaAluno.query.filter_by(rota_id=rota_id).all()
            for insc in inscricoes:
                usuarios_notificados.add(insc.aluno_id)
        elif viagem_id:
            viagem = db.session.get(Viagem, validate_uuid(viagem_id, "viagem_id"))
            rota_da_viagem = None
            if viagem and viagem.rota is not None:
                rota_da_viagem = viagem.rota
            elif viagem and viagem.horario_rota is not None:
                rota_da_viagem = viagem.horario_rota.rota
            if (
                not viagem
                or not rota_da_viagem
                or rota_da_viagem.organizacao_id != user.organizacao_id
            ):
                raise NotFoundError("Viagem não encontrada.")
            if viagem.status in (StatusViagem.FINALIZADA, StatusViagem.CANCELADA):
                raise ValidationError("Não é possível enviar aviso para uma viagem encerrada.")
            # The motorista sending the notice does not need a copy of it.
            motorista = viagem.motorista
            if (
                motorista is not None
                and str(motorista.id) != str(user_id)
                and motorista.status == UserStatus.ACTIVE
            ):
                usuarios_notificados.add(motorista.id)
            confirmados = AlunosConfirmados.query.filter_by(
                viagem_id=viagem_id, confirmacao=True
            ).all()
            for conf in confirmados:
                usuarios_notificados.add(conf.aluno_id)
            # On demand, before the buffer ends, the audience is the active requests.
            solicitacoes = SolicitacaoViagem.query.filter_by(
                viagem_id=viagem_id, status=StatusSolicitacao.ATIVA
            ).all()
            for solicitacao in solicitacoes:
                usuarios_notificados.add(solicitacao.aluno_id)
        else:
            raise ValidationError(
                "Informe o ID de uma rota (rota_id), viagem (viagem_id) ou usuário (destinatario_id)."
            )

        if not usuarios_notificados:
            raise NotFoundError("Nenhum usuário encontrado para receber este aviso.")

        try:
            for aluno_id in usuarios_notificados:
                NotificacaoService._criar_notificacao_interna(aluno_id, titulo, mensagem)

            db.session.commit()
            audit_logger.log_user_action(
                action="enviar_notificacao_massa",
                user_id=user_id,
                resource_type="notificacao",
                details={
                    "destinatario_id": destinatario_id,
                    "rota_id": rota_id,
                    "viagem_id": viagem_id,
                },
            )

            return {
                "message": f"Notificação enviada para {len(usuarios_notificados)} usuário(s) com sucesso."
            }

        except Exception:
            db.session.rollback()
            logger.exception("Erro ao disparar notificações")
            raise AppError("Erro ao enviar notificações", 500)

    @staticmethod
    def listar_notificacoes(user_id: str) -> list[Notificacao]:
        """List the logged-in user's notices"""
        return (
            Notificacao.query.filter_by(usuario_id=user_id)
            .order_by(Notificacao.created_at.desc())
            .all()
        )

    @staticmethod
    def marcar_lida(user_id: str, notificacao_id: str) -> dict[str, str]:
        notificacao = db.session.get(Notificacao, notificacao_id)
        if not notificacao or str(notificacao.usuario_id) != str(user_id):
            raise NotFoundError("Notificação não encontrada.")

        try:
            notificacao.enviada = True
            db.session.commit()
            return {"message": "Notificação marcada como lida."}
        except Exception:
            db.session.rollback()
            logger.exception("Erro ao atualizar notificação")
            raise AppError("Erro ao atualizar notificação", 500)

    @staticmethod
    def notificar_alunos_viagem_iniciada(viagem_id: str) -> None:
        """Find the students confirmed on the trip and send the departure notice."""
        try:
            confirmados = AlunosConfirmados.query.filter_by(
                viagem_id=viagem_id, confirmacao=True
            ).all()

            for conf in confirmados:
                NotificacaoService._criar_notificacao_interna(
                    usuario_id=conf.aluno_id,
                    titulo="🚌 Viagem Iniciada!",
                    mensagem="O motorista acabou de iniciar a rota. Acompanhe o trajeto no aplicativo!",
                )

            db.session.commit()
        except Exception as e:
            db.session.rollback()
            logger.error(
                f"Falha ao orquestrar notificações de início da viagem {viagem_id}: {str(e)}"
            )
