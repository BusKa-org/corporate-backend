"""On-demand operation parameters of the organization (RF-10, RF-11)."""

from typing import Any

from flask import current_app
from sqlalchemy import func
from sqlalchemy.dialects.postgresql import insert

from app.core.exceptions import ForbiddenError
from app.core.transaction import transactional
from app.models.base import db
from app.models.enum import UserRole
from app.models.parametros_operacao import ParametrosOperacao
from app.models.user import User


def parametros_da_organizacao(organizacao_id) -> ParametrosOperacao:
    """The saved row, or an unsaved one with the Settings defaults."""
    parametros = db.session.get(ParametrosOperacao, organizacao_id)
    if parametros is not None:
        return parametros
    config = current_app.config
    return ParametrosOperacao(
        organizacao_id=organizacao_id,
        minimo_alunos=config["OPERACAO_MINIMO_ALUNOS_PADRAO"],
        pausa_entre_viagens_minutos=config["OPERACAO_PAUSA_ENTRE_VIAGENS_MINUTOS_PADRAO"],
        antecedencia_motorista_minutos=config["OPERACAO_ANTECEDENCIA_MOTORISTA_MINUTOS_PADRAO"],
    )


def obter(user_id: str) -> ParametrosOperacao:
    user = db.session.get(User, user_id)
    if not user or user.role not in (UserRole.GESTOR, UserRole.MOTORISTA):
        raise ForbiddenError("Apenas gestores e motoristas podem ver os parâmetros da operação")
    return parametros_da_organizacao(user.organizacao_id)


def atualizar(user_id: str, data: dict[str, Any]) -> ParametrosOperacao:
    user = db.session.get(User, user_id)
    if not user or user.role != UserRole.GESTOR:
        raise ForbiddenError("Apenas gestores podem alterar os parâmetros da operação")

    valores = {
        "minimo_alunos": data["minimo_alunos"],
        "pausa_entre_viagens_minutos": data["pausa_entre_viagens_minutos"],
        "antecedencia_motorista_minutos": data["antecedencia_motorista_minutos"],
    }
    # Upsert: two concurrent first saves must not collide on the PK. updated_at is set
    # explicitly because onupdate is skipped here and a same-values save still counts.
    comando = insert(ParametrosOperacao).values(organizacao_id=user.organizacao_id, **valores)
    comando = comando.on_conflict_do_update(
        index_elements=[ParametrosOperacao.organizacao_id],
        set_={**valores, "updated_at": func.now()},
    )
    with transactional():
        db.session.execute(comando)

    parametros = db.session.get(ParametrosOperacao, user.organizacao_id, populate_existing=True)
    assert parametros is not None
    return parametros
