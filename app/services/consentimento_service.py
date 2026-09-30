"""Consentimento LGPD: aceite, revogação, estado e bloqueio."""

from functools import wraps
from typing import Any

from flask_jwt_extended import get_jwt_identity

from app.core.exceptions import ConflictError, ForbiddenError, ValidationError
from app.core.transaction import transactional
from app.models.base import db
from app.models.consentimento import ACEITE, REVOGACAO, Consentimento
from app.utils import audit_logger

# O texto do termo mora no app. O back só conhece o identificador da versão.
VERSAO_TERMO_VIGENTE = "1.0"


def consentimento_pendente(user_id: str) -> bool:
    """True quando o último evento do usuário não é um aceite da versão vigente."""
    ultimo = (
        db.session.query(Consentimento)
        .filter(Consentimento.usuario_id == user_id)
        .order_by(Consentimento.id.desc())
        .first()
    )
    if ultimo is None:
        return True
    if ultimo.acao != ACEITE:
        return True
    if ultimo.versao != VERSAO_TERMO_VIGENTE:
        return True
    return False


def get_estado(user_id: str) -> dict[str, Any]:
    return {
        "versao_vigente": VERSAO_TERMO_VIGENTE,
        "pendente": consentimento_pendente(user_id),
    }


def aceitar(user_id: str, versao: str) -> dict[str, Any]:
    if versao != VERSAO_TERMO_VIGENTE:
        raise ValidationError(
            f"Versão do termo inválida. A versão vigente é {VERSAO_TERMO_VIGENTE}."
        )

    with transactional():
        db.session.add(Consentimento(usuario_id=user_id, versao=versao, acao=ACEITE))

    audit_logger.log_user_action(
        action="consent_accept", user_id=user_id, resource_type="consentimento"
    )
    return get_estado(user_id)


def revogar(user_id: str) -> dict[str, Any]:
    if consentimento_pendente(user_id):
        raise ConflictError("Não há consentimento vigente para revogar")

    with transactional():
        db.session.add(
            Consentimento(usuario_id=user_id, versao=VERSAO_TERMO_VIGENTE, acao=REVOGACAO)
        )

    audit_logger.log_user_action(
        action="consent_revoke", user_id=user_id, resource_type="consentimento"
    )
    return get_estado(user_id)


def exige_consentimento(func):
    """Decorator para endpoints de passageiro. Vai abaixo de @jwt_required()."""

    @wraps(func)
    def wrapper(*args, **kwargs):
        if consentimento_pendente(get_jwt_identity()):
            raise ForbiddenError(
                "É necessário aceitar o termo de uso e a política de privacidade para continuar"
            )
        return func(*args, **kwargs)

    return wrapper
