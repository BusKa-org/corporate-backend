"""Notification service - management notifications for users."""

import logging
from datetime import UTC, datetime
from typing import Any

from firebase_admin import messaging

from app.core.exceptions import AppError, ForbiddenError, NotFoundError, ValidationError
from app.models.base import db
from app.models.enum import UserRole
from app.models.notificacao import Notificacao
from app.models.rota import RotaAluno
from app.models.user import User
from app.models.viagem import AlunosConfirmados
from app.utils import audit_logger

logger = logging.getLogger(__name__)


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
            try:
                mensagem_fcm = messaging.Message(
                    notification=messaging.Notification(
                        title=titulo,
                        body=mensagem,
                    ),
                    token=usuario.fcm_token,
                )
                response = messaging.send(mensagem_fcm)
                logger.info(f"Push enviado com sucesso para {usuario.email}. ID: {response}")

            except Exception as e:
                logger.error(
                    f"Falha ao enviar Push Notification via Firebase para {usuario.email}: {str(e)}"
                )

        return nova

    @staticmethod
    def notificar_por_gestor(user_id: str, dados: dict[str, Any]) -> dict[str, Any]:
        from app.models.viagem import Viagem

        user = db.session.get(User, user_id)
        if not user:
            raise ForbiddenError("Usuário não encontrado.")

        viagem_id = dados.get("viagem_id")

        # Motoristas can broadcast to their own active trip only
        if user.role == UserRole.MOTORISTA:
            if not viagem_id:
                raise ForbiddenError("Motoristas devem informar viagem_id para enviar avisos.")
            viagem = db.session.get(Viagem, viagem_id)
            if not viagem or str(viagem.motorista_id) != str(user_id):
                raise ForbiddenError(
                    "Você só pode enviar avisos para viagens que você está conduzindo."
                )
            from app.models.enum import StatusViagem

            if viagem.status != StatusViagem.EM_ANDAMENTO:
                raise ForbiddenError("Você só pode enviar avisos durante uma viagem em andamento.")
        elif user.role != UserRole.GESTOR:
            raise ForbiddenError("Apenas gestores ou motoristas podem enviar comunicados.")

        titulo = dados.get("titulo")
        mensagem = dados.get("mensagem")
        rota_id = dados.get("rota_id")
        viagem_id = dados.get("viagem_id")

        if not titulo or not mensagem:
            raise ValidationError("Título e mensagem são obrigatórios.")

        usuarios_notificados = set()

        if rota_id:
            inscricoes = RotaAluno.query.filter_by(rota_id=rota_id).all()
            for insc in inscricoes:
                usuarios_notificados.add(insc.aluno_id)
        elif viagem_id:
            confirmados = AlunosConfirmados.query.filter_by(
                viagem_id=viagem_id, confirmacao=True
            ).all()
            for conf in confirmados:
                usuarios_notificados.add(conf.aluno_id)
        else:
            raise ValidationError("Informe o ID de uma rota (rota_id) ou viagem (viagem_id).")

        if not usuarios_notificados:
            raise NotFoundError("Nenhum aluno encontrado para receber este aviso.")

        try:
            for aluno_id in usuarios_notificados:
                NotificacaoService._criar_notificacao_interna(aluno_id, titulo, mensagem)

            db.session.commit()
            audit_logger.log_user_action(
                action="enviar_notificacao_massa", user_id=user_id, resource_type="notificacao"
            )

            return {
                "message": f"Notificação enviada para {len(usuarios_notificados)} aluno(s) com sucesso."
            }

        except Exception as e:
            db.session.rollback()
            logger.error(f"Erro ao disparar notificações: {e}")
            raise AppError(f"Erro ao enviar notificações: {str(e)}", 500)

    @staticmethod
    def listar_notificacoes(user_id: str) -> list[Notificacao]:
        """Lista avisos do usuário logado"""
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
        except Exception as e:
            db.session.rollback()
            raise AppError(f"Erro ao atualizar notificação: {str(e)}", 500)

    @staticmethod
    def notificar_alunos_viagem_iniciada(viagem_id: str) -> None:
        """Busca os alunos confirmados na viagem e dispara o aviso de partida."""
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
