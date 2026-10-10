"""Student (Aluno) service - profile management and gestor queries."""

import logging
from typing import Any, cast

from app.core.exceptions import (
    AppError,
    ForbiddenError,
    NotFoundError,
)
from app.models.base import db
from app.models.enum import UserStatus
from app.models.geo import Endereco, Ponto
from app.models.user import Aluno
from app.services.user_service import _get_gestor_or_403

logger = logging.getLogger(__name__)


def update_me(user_id: str, data: dict[str, Any]) -> Aluno:
    """
    Atualiza perfil do aluno.

    Returns: Aluno object
    Raises: NotFoundError, AppError
    """
    aluno = db.session.get(Aluno, user_id)
    if not aluno:
        raise NotFoundError("Aluno não encontrado")

    try:
        for field in (
            "nome",
            "telefone",
            "matricula",
            "nome_responsavel",
            "cpf_responsavel",
        ):
            if field in data:
                setattr(aluno, field, data[field])

        if "endereco_casa" in data:
            end_data = data["endereco_casa"]

            if aluno.ponto_casa:
                ponto_casa = cast(Ponto, aluno.ponto_casa)
                ponto_casa.latitude = end_data.get("latitude")
                ponto_casa.longitude = end_data.get("longitude")
                if "nome" in data:
                    ponto_casa.apelido = f"Casa: {data['nome']}"

                endereco_bd = Endereco.query.filter_by(ponto_id=aluno.ponto_casa_id).first()

                if endereco_bd:
                    endereco_bd.logradouro = end_data.get("logradouro")
                    endereco_bd.numero = end_data.get("numero")
                    endereco_bd.bairro = end_data.get("bairro")
                    endereco_bd.cidade = end_data.get("cidade")
                    endereco_bd.cep = end_data.get("cep")
                else:
                    novo_end = Endereco(
                        ponto_id=aluno.ponto_casa_id,
                        logradouro=end_data.get("logradouro"),
                        numero=end_data.get("numero"),
                        bairro=end_data.get("bairro"),
                        cidade=end_data.get("cidade"),
                        cep=end_data.get("cep"),
                    )
                    db.session.add(novo_end)
            else:
                novo_ponto = Ponto(
                    organizacao_id=aluno.organizacao_id,
                    latitude=end_data.get("latitude"),
                    longitude=end_data.get("longitude"),
                    apelido=f"Casa: {data.get('nome', aluno.nome)}",
                )
                db.session.add(novo_ponto)
                db.session.flush()

                novo_end = Endereco(
                    ponto_id=novo_ponto.id,
                    logradouro=end_data.get("logradouro"),
                    numero=end_data.get("numero"),
                    bairro=end_data.get("bairro"),
                    cidade=end_data.get("cidade"),
                    cep=end_data.get("cep"),
                )
                db.session.add(novo_end)

                aluno.ponto_casa_id = novo_ponto.id

        db.session.commit()
        return aluno

    except Exception as e:
        db.session.rollback()
        logger.error(f"Error updating student profile: {e}")
        raise AppError(f"Erro ao atualizar perfil: {str(e)}", 500)


def get_aluno_by_id(gestor_id: str, aluno_id: str) -> Aluno:
    """
    Gestor retrieves full details for a single aluno.

    Raises: ForbiddenError, NotFoundError
    """
    gestor = _get_gestor_or_403(gestor_id, "Apenas gestores podem consultar alunos")
    aluno = db.session.get(Aluno, aluno_id)

    if not aluno:
        raise NotFoundError("Aluno não encontrado")
    if str(aluno.organizacao_id) != str(gestor.organizacao_id):
        raise ForbiddenError("Aluno não pertence à sua organização")

    return aluno


def list_alunos_gestor(gestor_id: str, status: str | None = None) -> list[Aluno]:
    """
    Lista alunos da organização (apenas para gestores).
    Optionally filter by status (e.g. 'PENDING_APPROVAL').

    Returns: List of Aluno objects
    Raises: ForbiddenError
    """
    gestor = _get_gestor_or_403(gestor_id, "Apenas gestores podem listar alunos")
    q = db.session.query(Aluno).filter_by(organizacao_id=gestor.organizacao_id)
    if status:
        try:
            q = q.filter(Aluno.status == UserStatus[status])
        except KeyError:
            pass
    return q.all()
