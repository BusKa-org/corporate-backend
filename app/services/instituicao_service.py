"""Institution service - schools and universities management."""

import logging
from typing import Any

from sqlalchemy import or_
from sqlalchemy.exc import IntegrityError

from app.core.exceptions import (
    AppError,
    ConflictError,
    ForbiddenError,
    NotFoundError,
    ValidationError,
)
from app.models.base import db
from app.models.enum import UserRole
from app.models.geo import Endereco, Instituicao, Ponto
from app.models.organizacao import Organizacao
from app.models.user import User

logger = logging.getLogger(__name__)


def create_instituicao(gestor_id: str, data: dict[str, Any]) -> Instituicao:
    """
    Create a new institution (gestor only).

    Raises: ForbiddenError, ValidationError, ConflictError, AppError
    """
    user = db.session.get(User, gestor_id)
    if not user or user.role != UserRole.GESTOR:
        raise ForbiddenError("Permissão negada. Apenas gestores criam instituições.")

    nome = data.get("nome")
    cnpj = data.get("cnpj")
    tipo = data.get("tipo")
    end_data = data.get("endereco")

    if not end_data:
        raise ValidationError("Dados de endereço são obrigatórios")

    uf = end_data.get("uf")
    if uf:
        uf = uf.upper()
    else:
        organizacao = db.session.get(Organizacao, user.organizacao_id)
        if organizacao:
            uf = organizacao.estado
    if not uf:
        raise ValidationError(
            "Organização sem UF cadastrada. Informe a UF no endereço ou peça "
            "ao administrador para cadastrar o estado da organização."
        )

    try:
        novo_ponto = Ponto(
            organizacao_id=user.organizacao_id,
            latitude=end_data.get("latitude"),
            longitude=end_data.get("longitude"),
            # apelido is String(100) but nome allows 200, so the label is cut.
            apelido=f"Inst: {nome}"[:100],
        )
        db.session.add(novo_ponto)
        db.session.flush()

        nova_inst = Instituicao(
            nome=nome,
            cnpj=cnpj,
            tipo=tipo,
            # Entered by a gestor, not imported from EMEC/INEP (same as seed.py).
            fonte="MANUAL",
            codigo_externo=cnpj,
            uf=uf,
            organizacao_id=user.organizacao_id,
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

    except IntegrityError as e:
        db.session.rollback()
        # Global constraint: catches duplicates in this and in other organizations.
        constraint = getattr(getattr(e.orig, "diag", None), "constraint_name", None)
        if constraint == "uq_instituicao_fonte_codigo_externo":
            raise ConflictError("Já existe uma instituição com este CNPJ", field="cnpj")
        logger.exception("Error saving institution")
        raise AppError("Erro ao salvar instituição", 500)
    except Exception:
        db.session.rollback()
        logger.exception("Error saving institution")
        raise AppError("Erro ao salvar instituição", 500)


def list_all(gestor_id: str) -> list[Instituicao]:
    """List all institutions for user's organizacao."""
    user = db.session.get(User, gestor_id)
    if not user:
        raise NotFoundError("Usuário não encontrado")

    return Instituicao.query.filter(Instituicao.organizacao_id == user.organizacao_id).all()


def list_all_public(filters: dict[str, Any]) -> list[Instituicao]:
    """List all institutions (public - for student registration)."""
    query = Instituicao.query.join(Organizacao)

    search = filters.get("search")
    limit = filters.get("limit", 10)

    if search:
        search_term = f"%{search}%"
        query = query.filter(
            or_(
                Instituicao.nome.ilike(search_term),
                Instituicao.sigla.ilike(search_term),
                Instituicao.uf.ilike(search_term),
                Organizacao.nome.ilike(search_term),
            )
        )

    query = query.order_by(Instituicao.nome.asc()).limit(limit)

    return query.all()


def get_by_id(gestor_id: str, inst_id: str) -> Instituicao:
    """
    Get institution by ID (with tenant check).

    Raises: NotFoundError, ForbiddenError
    """
    user = db.session.get(User, gestor_id)
    if not user:
        raise NotFoundError("Usuário não encontrado")

    inst = db.session.get(Instituicao, inst_id)
    if not inst:
        raise NotFoundError("Instituição não encontrada")

    if inst.ponto.organizacao_id != user.organizacao_id:
        raise ForbiddenError("Acesso negado")

    return inst


def delete_instituicao(gestor_id: str, inst_id: str) -> None:
    """
    Delete an institution (gestor only).

    Raises: ForbiddenError, NotFoundError, AppError
    """
    user = db.session.get(User, gestor_id)
    if not user or user.role != UserRole.GESTOR:
        raise ForbiddenError("Apenas gestores podem remover instituições")

    inst = db.session.get(Instituicao, inst_id)
    if not inst:
        raise NotFoundError("Instituição não encontrada")

    if inst.ponto.organizacao_id != user.organizacao_id:
        raise ForbiddenError("Acesso negado")

    try:
        db.session.delete(inst.ponto)
        db.session.commit()
    except Exception as e:
        db.session.rollback()
        logger.error(f"Error deleting institution: {e}")
        raise AppError(f"Erro ao remover instituição: {str(e)}", 500)
