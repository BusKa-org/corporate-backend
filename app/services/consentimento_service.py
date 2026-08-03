"""RF-09 — consentimento LGPD versionado.

Uma linha por aceite, nunca sobrescrita. O que libera as funcionalidades
principais é existir um aceite *não revogado* para a versão vigente do termo:
quando a versão muda, o aceite antigo continua no histórico (é a prova do
consentimento dado à época) mas deixa de valer.
"""

import logging
from datetime import UTC, datetime
from functools import lru_cache
from typing import Any

from flask import current_app

from app.core.exceptions import NotFoundError
from app.core.transaction import transactional
from app.models.base import db
from app.models.consentimento import Consentimento
from app.models.user import User
from app.utils import audit_logger

logger = logging.getLogger(__name__)


@lru_cache(maxsize=1)
def _versao_padrao() -> str:
    """Default do ambiente, lido uma vez. `app.config` tem precedência."""
    from app.core.config import Settings

    return Settings().TERMO_VERSAO


def versao_vigente() -> str:
    """Versão do termo em vigor agora."""
    return current_app.config.get("TERMO_VERSAO") or _versao_padrao()


def _get_user_or_404(user_id: str) -> User:
    user = db.session.get(User, user_id)
    if not user:
        raise NotFoundError("Usuário não encontrado")
    return user


def tem_consentimento_vigente(user_id: str) -> bool:
    """Guarda de acesso: o usuário aceitou a versão em vigor e não revogou?

    Usada pelos fluxos que dependem de consentimento (solicitação de viagem,
    RF-10). Recusar o termo não desloga ninguém — apenas mantém o acesso
    restrito, conforme o fluxo secundário 1 do RF-09.
    """
    return (
        db.session.query(Consentimento.id)
        .filter_by(usuario_id=user_id, versao_termo=versao_vigente(), revogado_em=None)
        .first()
        is not None
    )


def get_status(user_id: str) -> dict[str, Any]:
    """Situação do titular perante a versão vigente do termo."""
    _get_user_or_404(user_id)
    versao = versao_vigente()

    aceite = (
        db.session.query(Consentimento)
        .filter_by(usuario_id=user_id, versao_termo=versao, revogado_em=None)
        .order_by(Consentimento.aceito_em.desc())
        .first()
    )

    return {
        "versao_termo": versao,
        "aceito": aceite is not None,
        "aceito_em": aceite.aceito_em if aceite else None,
    }


def registrar_aceite(user_id: str, ip_origem: str | None = None) -> Consentimento:
    """Registra o aceite do titular para a versão vigente do termo."""
    _get_user_or_404(user_id)
    versao = versao_vigente()

    with transactional():
        aceite = Consentimento(
            usuario_id=user_id,
            versao_termo=versao,
            aceito_em=datetime.now(UTC),
            ip_origem=ip_origem,
        )
        db.session.add(aceite)

    audit_logger.log_user_action(
        action="consentimento_aceito",
        user_id=user_id,
        resource_type="consentimento",
        resource_id=str(aceite.id),
        details={"versao_termo": versao},
    )
    return aceite


def revogar_consentimentos(user_id: str) -> int:
    """Revoga todos os aceites ativos do titular (RF-20).

    Não apaga as linhas: a LGPD exige poder comprovar quando o consentimento
    foi dado e quando foi retirado. Não faz commit — quem chama controla a
    transação.
    """
    return (
        db.session.query(Consentimento)
        .filter_by(usuario_id=user_id, revogado_em=None)
        .update({"revogado_em": datetime.now(UTC)}, synchronize_session=False)
    )
