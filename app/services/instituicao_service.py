"""Institution service - schools and universities management."""

import logging
from typing import Any

from sqlalchemy import or_

from app.core.exceptions import AppError, ForbiddenError, NotFoundError, ValidationError
from app.models.base import db
from app.models.enum import TipoInstituicao, UserRole
from app.models.geo import Endereco, Instituicao, Ponto
from app.models.prefeitura import Prefeitura
from app.models.user import User

logger = logging.getLogger(__name__)


def create_instituicao(gestor_id: str, data: dict[str, Any]) -> Instituicao:
    """
    Create a new institution (gestor only).

    Raises: ForbiddenError, ValidationError, AppError
    """
    user = User.query.get(gestor_id)
    if not user or user.role != UserRole.GESTOR:
        raise ForbiddenError("Permissão negada. Apenas gestores criam instituições.")

    nome = data.get("nome")
    cnpj = data.get("cnpj")
    tipo_str = data.get("tipo", "ESCOLA_PUBLICA")
    end_data = data.get("endereco")

    if not end_data:
        raise ValidationError("Dados de endereço são obrigatórios")

    try:
        novo_ponto = Ponto(
            prefeitura_id=user.prefeitura_id,
            latitude=end_data.get("latitude"),
            longitude=end_data.get("longitude"),
            apelido=f"Inst: {nome}",
        )
        db.session.add(novo_ponto)
        db.session.flush()

        nova_inst = Instituicao(
            nome=nome,
            cnpj=cnpj,
            tipo=TipoInstituicao(tipo_str),
            ponto_id=novo_ponto.id,
        )
        db.session.add(nova_inst)

        novo_endereco = Endereco(
            logradouro=end_data.get("logradouro"),
            numero=end_data.get("numero"),
            bairro=end_data.get("bairro"),
            cidade=end_data.get("cidade"),
            cep=end_data.get("cep"),
            ponto_id=novo_ponto.id,
        )
        db.session.add(novo_endereco)

        db.session.commit()
        return nova_inst

    except Exception as e:
        db.session.rollback()
        raise AppError(f"Erro ao salvar instituição: {str(e)}", 500)


def list_all(gestor_id: str) -> list[Instituicao]:
    """List all institutions for user's prefeitura."""
    user = User.query.get(gestor_id)
    if not user:
        raise NotFoundError("Usuário não encontrado")

    return Instituicao.query.filter(Instituicao.prefeitura_id == user.prefeitura_id).all()


def list_all_public(filters: dict[str, Any]) -> list[Instituicao]:
    """List all institutions (public - for student registration)."""
    query = Instituicao.query.join(Prefeitura)

    search = filters.get("search")
    limit = filters.get("limit", 10)

    if search:
        search_term = f"%{search}%"
        query = query.filter(
            or_(
                Instituicao.nome.ilike(search_term),
                Instituicao.sigla.ilike(search_term),
                Instituicao.uf.ilike(search_term),
                Prefeitura.nome.ilike(search_term),
            )
        )

    query = query.order_by(Instituicao.nome.asc()).limit(limit)

    return query.all()


def get_by_id(gestor_id: str, inst_id: str) -> Instituicao:
    """
    Get institution by ID (with tenant check).

    Raises: NotFoundError, ForbiddenError
    """
    user = User.query.get(gestor_id)
    if not user:
        raise NotFoundError("Usuário não encontrado")

    inst = Instituicao.query.get(inst_id)
    if not inst:
        raise NotFoundError("Instituição não encontrada")

    if inst.ponto.prefeitura_id != user.prefeitura_id:
        raise ForbiddenError("Acesso negado")

    return inst


def delete_instituicao(gestor_id: str, inst_id: str) -> None:
    """
    Delete an institution (gestor only).

    Raises: ForbiddenError, NotFoundError, AppError
    """
    user = User.query.get(gestor_id)
    if not user or user.role != UserRole.GESTOR:
        raise ForbiddenError("Apenas gestores podem remover instituições")

    inst = Instituicao.query.get(inst_id)
    if not inst:
        raise NotFoundError("Instituição não encontrada")

    if inst.ponto.prefeitura_id != user.prefeitura_id:
        raise ForbiddenError("Acesso negado")

    try:
        db.session.delete(inst.ponto)
        db.session.commit()
    except Exception as e:
        db.session.rollback()
        logger.error(f"Error deleting institution: {e}")
        raise AppError(f"Erro ao remover instituição: {str(e)}", 500)
