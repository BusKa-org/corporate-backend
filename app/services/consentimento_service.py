"""LGPD consent: acceptance, revocation, state and blocking."""

from functools import wraps
from typing import Any

from flask import request
from flask_jwt_extended import get_jwt_identity, verify_jwt_in_request
from flask_jwt_extended.exceptions import JWTExtendedException
from jwt.exceptions import PyJWTError

from app.core.exceptions import ConflictError, ForbiddenError, ValidationError
from app.core.transaction import transactional
from app.models.base import db
from app.models.consentimento import ACEITE, REVOGACAO, Consentimento
from app.models.enum import UserRole
from app.models.user import User
from app.utils import audit_logger

# The terms text lives in the app. The backend only knows the version identifier.
VERSAO_TERMO_VIGENTE = "1.0"
CONSENTIMENTO_OBRIGATORIO = (
    "É necessário aceitar o termo de uso e a política de privacidade para continuar"
)
# What a driver without consent can still reach: auth, the terms themselves and self-service
# (LGPD: deleting or editing the account must not depend on accepting the terms).
# Exact paths, so a new route under one of them is blocked until listed here.
ROTAS_LIVRES_PARA_MOTORISTA = (
    "/v1/consentimento",
    "/v1/users/me",
    "/v1/users/change-password",
    "/v1/users/fcm-token",
)


def consentimento_pendente(user_id: str) -> bool:
    """True when the user's latest event is not an acceptance of the current version."""
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
    """Decorator for passenger endpoints. Goes below @jwt_required()."""

    @wraps(func)
    def wrapper(*args, **kwargs):
        if consentimento_pendente(get_jwt_identity()):
            raise ForbiddenError(CONSENTIMENTO_OBRIGATORIO)
        return func(*args, **kwargs)

    return wrapper


def exigir_consentimento_do_motorista() -> None:
    """before_request hook (RF-09): a driver uses no feature without the current consent,
    whatever the status and however the account became ACTIVE (e.g. gestor activation).
    """
    # CORS preflight carries no token, and flask-jwt-extended skips it.
    if request.method == "OPTIONS" or request.path.startswith("/v1/auth/"):
        return
    if request.path in ROTAS_LIVRES_PARA_MOTORISTA:
        return
    try:
        verify_jwt_in_request(optional=True)
    except (JWTExtendedException, PyJWTError):
        # Bad, expired or revoked token: the route's own @jwt_required answers it.
        return
    user_id = get_jwt_identity()
    if user_id is None:
        return
    user = db.session.get(User, user_id)
    if user is None or user.role != UserRole.MOTORISTA:
        return
    if consentimento_pendente(user_id):
        raise ForbiddenError(CONSENTIMENTO_OBRIGATORIO)
