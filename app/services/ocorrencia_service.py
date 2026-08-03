"""Ocorrência (issue reporting) service."""

import logging
from typing import Any

from app.core.exceptions import AppError, ForbiddenError, NotFoundError, ValidationError
from app.models.base import db
from app.models.enum import StatusOcorrencia, TipoOcorrencia, UserRole
from app.models.ocorrencia import Ocorrencia
from app.models.user import User
from app.models.viagem import Viagem
from app.utils import audit_logger

logger = logging.getLogger(__name__)


class OcorrenciaService:

    @staticmethod
    def criar(user_id: str, dados: dict[str, Any]) -> Ocorrencia:
        """
        Aluno ou Motorista reporta um problema.
        Automatically notifies the gestor of the prefeitura.
        """
        user = db.session.get(User, user_id)
        if not user or user.role not in (UserRole.ALUNO, UserRole.MOTORISTA):
            raise ForbiddenError("Apenas alunos e motoristas podem reportar ocorrências.")

        tipo_str = dados.get("tipo")
        try:
            tipo = TipoOcorrencia[tipo_str] if tipo_str else None
        except KeyError:
            tipo = None
        if not tipo:
            raise ValidationError(
                f"Tipo inválido. Valores válidos: {[t.value for t in TipoOcorrencia]}"
            )

        viagem_id = dados.get("viagem_id")
        if viagem_id:
            viagem = db.session.get(Viagem, viagem_id)
            if not viagem:
                raise NotFoundError("Viagem não encontrada.")

        try:
            ocorrencia = Ocorrencia(
                autor_id=user_id,
                viagem_id=viagem_id,
                tipo=tipo,
                descricao=dados.get("descricao"),
                status=StatusOcorrencia.ABERTA,
            )
            db.session.add(ocorrencia)
            db.session.flush()

            # Notify the gestor of this prefeitura
            OcorrenciaService._notificar_gestores(user, ocorrencia)

            db.session.commit()
            audit_logger.log_user_action(
                action="criar_ocorrencia",
                user_id=user_id,
                resource_type="ocorrencia",
                resource_id=str(ocorrencia.id),
            )
            return ocorrencia

        except AppError:
            db.session.rollback()
            raise
        except Exception as e:
            db.session.rollback()
            logger.error(f"Erro ao criar ocorrência: {e}")
            raise AppError(f"Erro ao registrar ocorrência: {str(e)}", 500)

    @staticmethod
    def _notificar_gestores(autor: User, ocorrencia: Ocorrencia) -> None:
        from app.models.user import Gestor
        from app.services.notificacao_service import NotificacaoService

        tipo_label = {
            TipoOcorrencia.ATRASO: "Atraso",
            TipoOcorrencia.SUPERLOTACAO: "Superlotação",
            TipoOcorrencia.COMPORTAMENTO: "Comportamento",
            TipoOcorrencia.CANCELAMENTO: "Cancelamento",
            TipoOcorrencia.OUTRO: "Outro",
        }.get(ocorrencia.tipo, ocorrencia.tipo.value)

        gestores = db.session.query(Gestor).filter_by(prefeitura_id=autor.prefeitura_id).all()
        for gestor in gestores:
            NotificacaoService._criar_notificacao_interna(
                usuario_id=str(gestor.id),
                titulo=f"Nova Ocorrência: {tipo_label}",
                mensagem=(f"{autor.nome} reportou: " f"{ocorrencia.descricao or tipo_label}"),
            )

    @staticmethod
    def listar(gestor_id: str, status: str | None = None) -> list[Ocorrencia]:
        """Gestor lista ocorrências da sua prefeitura."""
        from app.services.user_service import _get_gestor_or_403

        gestor = _get_gestor_or_403(gestor_id, "Apenas gestores podem listar ocorrências.")

        q = (
            db.session.query(Ocorrencia)
            .join(User, Ocorrencia.autor_id == User.id)
            .filter(User.prefeitura_id == gestor.prefeitura_id)
            .order_by(Ocorrencia.created_at.desc())
        )
        if status:
            try:
                q = q.filter(Ocorrencia.status == StatusOcorrencia[status])
            except KeyError:
                pass
        return q.all()

    @staticmethod
    def resolver(gestor_id: str, ocorrencia_id: str) -> Ocorrencia:
        """Gestor marca uma ocorrência como resolvida."""
        from app.services.user_service import _get_gestor_or_403

        _get_gestor_or_403(gestor_id, "Apenas gestores podem resolver ocorrências.")

        ocorrencia = db.session.get(Ocorrencia, ocorrencia_id)
        if not ocorrencia:
            raise NotFoundError("Ocorrência não encontrada.")
        if ocorrencia.status == StatusOcorrencia.RESOLVIDA:
            raise ValidationError("Ocorrência já foi resolvida.")

        try:
            ocorrencia.status = StatusOcorrencia.RESOLVIDA
            db.session.commit()
            return ocorrencia
        except Exception as e:
            db.session.rollback()
            raise AppError(f"Erro ao resolver ocorrência: {str(e)}", 500)
