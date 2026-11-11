"""Incident (ocorrencia) reporting service."""

import logging
from typing import Any

from app.core.exceptions import AppError, ForbiddenError, NotFoundError, ValidationError
from app.models.base import db
from app.models.enum import StatusOcorrencia, TipoOcorrencia, UserRole
from app.models.ocorrencia import Ocorrencia
from app.models.user import User
from app.models.viagem import Viagem
from app.utils import audit_logger
from app.utils.validators import validate_uuid

logger = logging.getLogger(__name__)


def _organizacao_da_viagem(viagem: Viagem) -> Any:
    """The route's organization; the driver's or vehicle's if the route was deleted (SET NULL)."""
    rota = viagem.rota or (viagem.horario_rota.rota if viagem.horario_rota else None)
    dono = rota or viagem.motorista or viagem.veiculo
    return dono.organizacao_id if dono else None


class OcorrenciaService:

    @staticmethod
    def criar(user_id: str, dados: dict[str, Any]) -> Ocorrencia:
        """Student or Driver reports a problem; the organization's manager is notified."""
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
            viagem = db.session.get(Viagem, validate_uuid(viagem_id, "ID da viagem"))
            # Another organization's trip gets the same answer as a missing one.
            if not viagem or _organizacao_da_viagem(viagem) != user.organizacao_id:
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

        gestores = db.session.query(Gestor).filter_by(organizacao_id=autor.organizacao_id).all()
        for gestor in gestores:
            NotificacaoService._criar_notificacao_interna(
                usuario_id=str(gestor.id),
                titulo=f"Nova Ocorrência: {tipo_label}",
                mensagem=(f"{autor.nome} reportou: " f"{ocorrencia.descricao or tipo_label}"),
            )

    @staticmethod
    def listar(gestor_id: str, status: str | None = None) -> list[Ocorrencia]:
        """Manager lists their organization's incidents."""
        from app.services.user_service import _get_gestor_or_403

        gestor = _get_gestor_or_403(gestor_id, "Apenas gestores podem listar ocorrências.")

        q = (
            db.session.query(Ocorrencia)
            .join(User, Ocorrencia.autor_id == User.id)
            .filter(User.organizacao_id == gestor.organizacao_id)
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
        """Manager marks an incident as resolved."""
        from app.services.user_service import _get_gestor_or_403

        gestor = _get_gestor_or_403(gestor_id, "Apenas gestores podem resolver ocorrências.")

        # Org filter inside the locked query: another org's manager never locks the row.
        # 404, not 403: listar() hides other organizations' incidents, so don't reveal they exist.
        # of=Ocorrencia: the joined-eager autor is an outer join, which FOR UPDATE can't lock.
        ocorrencia = (
            db.session.query(Ocorrencia)
            .join(User, Ocorrencia.autor_id == User.id)
            .filter(Ocorrencia.id == ocorrencia_id, User.organizacao_id == gestor.organizacao_id)
            .with_for_update(of=Ocorrencia, key_share=True)
            .populate_existing()
            .one_or_none()
        )
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
