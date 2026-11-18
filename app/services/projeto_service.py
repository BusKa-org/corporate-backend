"""Projects of the organization's alunos, managed by the gestor."""

from typing import Any

from sqlalchemy import func
from sqlalchemy.exc import IntegrityError

from app.core.exceptions import ConflictError, NotFoundError, ValidationError
from app.models.base import db
from app.models.projeto import Projeto
from app.models.user import Aluno
from app.services.user_service import _get_gestor_or_403
from app.utils.validators import validate_uuid

NOME_DUPLICADO = "Já existe um projeto com este nome na organização"


def projeto_da_organizacao(organizacao_id, projeto_id: str) -> Projeto:
    """Another organization's project is reported as missing, not forbidden."""
    projeto = db.session.get(Projeto, validate_uuid(projeto_id, "projeto_id"))
    if projeto is None or projeto.organizacao_id != organizacao_id:
        raise NotFoundError("Projeto não encontrado")
    return projeto


def _nome_em_uso(organizacao_id, nome: str, ignorar_id=None) -> bool:
    query = db.session.query(Projeto).filter(
        Projeto.organizacao_id == organizacao_id,
        func.lower(Projeto.nome) == nome.lower(),
    )
    if ignorar_id is not None:
        query = query.filter(Projeto.id != ignorar_id)
    return db.session.query(query.exists()).scalar()


def _salvar(projeto: Projeto) -> Projeto:
    db.session.add(projeto)
    try:
        db.session.commit()
    except IntegrityError as e:
        # Two concurrent saves with the same name both pass _nome_em_uso; the unique index wins.
        db.session.rollback()
        raise ConflictError(NOME_DUPLICADO, field="nome") from e
    return projeto


def listar(gestor_id: str) -> list[Projeto]:
    gestor = _get_gestor_or_403(gestor_id, "Apenas gestores podem listar projetos")
    query = db.session.query(Projeto).filter(Projeto.organizacao_id == gestor.organizacao_id)
    return query.order_by(Projeto.nome.asc()).all()


def criar(gestor_id: str, data: dict[str, Any]) -> Projeto:
    gestor = _get_gestor_or_403(
        gestor_id, "Apenas gestores podem criar projetos", require_active=True
    )
    nome = data["nome"]
    if _nome_em_uso(gestor.organizacao_id, nome):
        raise ConflictError(NOME_DUPLICADO, field="nome")

    projeto = Projeto(organizacao_id=gestor.organizacao_id, nome=nome, ativo=True)
    return _salvar(projeto)


def atualizar(gestor_id: str, projeto_id: str, data: dict[str, Any]) -> Projeto:
    """Rename and/or (de)activate. Alunos stay linked to a deactivated project."""
    gestor = _get_gestor_or_403(
        gestor_id, "Apenas gestores podem alterar projetos", require_active=True
    )
    projeto = projeto_da_organizacao(gestor.organizacao_id, projeto_id)

    if "nome" in data:
        nome = data["nome"]
        if _nome_em_uso(gestor.organizacao_id, nome, ignorar_id=projeto.id):
            raise ConflictError(NOME_DUPLICADO, field="nome")
        projeto.nome = nome
    if "ativo" in data:
        projeto.ativo = data["ativo"]

    return _salvar(projeto)


def definir_projeto_do_aluno(gestor_id: str, aluno_id: str, projeto_id: str | None) -> Aluno:
    """Assign the aluno to a project, or unassign with projeto_id None."""
    gestor = _get_gestor_or_403(
        gestor_id, "Apenas gestores podem definir o projeto do aluno", require_active=True
    )
    aluno = db.session.get(Aluno, validate_uuid(aluno_id, "aluno_id"))
    if aluno is None or aluno.organizacao_id != gestor.organizacao_id:
        raise NotFoundError("Aluno não encontrado")

    if projeto_id is None:
        aluno.projeto_id = None
    else:
        projeto = projeto_da_organizacao(gestor.organizacao_id, projeto_id)
        if not projeto.ativo:
            raise ValidationError("Projeto desativado não recebe alunos")
        aluno.projeto_id = projeto.id

    db.session.commit()
    return aluno
