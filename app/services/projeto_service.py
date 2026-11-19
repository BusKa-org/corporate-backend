"""Projects of the organization's alunos, managed by the gestor."""

from typing import Any

from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError

from app.core.exceptions import ConflictError, NotFoundError, ValidationError
from app.models.base import db
from app.models.enum import UserStatus
from app.models.projeto import Projeto
from app.models.user import Aluno, User
from app.services.user_service import _get_gestor_or_403
from app.utils.validators import validate_uuid


def projeto_da_organizacao(organizacao_id, projeto_id: str, travar: bool = False) -> Projeto:
    """Another organization's project is reported as missing, not forbidden."""
    query = db.session.query(Projeto).filter(Projeto.id == validate_uuid(projeto_id, "projeto_id"))
    if travar:
        # FOR SHARE: a concurrent deactivation waits until this assignment commits.
        query = query.with_for_update(read=True).populate_existing()
    projeto = query.one_or_none()
    if projeto is None or projeto.organizacao_id != organizacao_id:
        raise NotFoundError("Projeto não encontrado")
    return projeto


def _salvar(projeto: Projeto) -> Projeto:
    db.session.add(projeto)
    try:
        db.session.commit()
    except IntegrityError as e:
        db.session.rollback()
        # The case-insensitive unique index is the only duplicate-name check.
        constraint = getattr(getattr(e.orig, "diag", None), "constraint_name", None)
        if constraint == "uq_projeto_organizacao_nome":
            raise ConflictError(
                "Já existe um projeto com este nome na organização", field="nome"
            ) from e
        raise
    return projeto


def listar(gestor_id: str) -> list[Projeto]:
    gestor = _get_gestor_or_403(gestor_id, "Apenas gestores podem listar projetos")
    query = db.session.query(Projeto).filter(Projeto.organizacao_id == gestor.organizacao_id)
    return query.order_by(func.lower(Projeto.nome).asc()).all()


def criar(gestor_id: str, data: dict[str, Any]) -> Projeto:
    gestor = _get_gestor_or_403(
        gestor_id, "Apenas gestores podem criar projetos", require_active=True
    )
    projeto = Projeto(organizacao_id=gestor.organizacao_id, nome=data["nome"], ativo=True)
    return _salvar(projeto)


def atualizar(gestor_id: str, projeto_id: str, data: dict[str, Any]) -> Projeto:
    """Rename and/or (de)activate. Alunos stay linked to a deactivated project."""
    gestor = _get_gestor_or_403(
        gestor_id, "Apenas gestores podem alterar projetos", require_active=True
    )
    projeto = projeto_da_organizacao(gestor.organizacao_id, projeto_id)

    if "nome" in data:
        projeto.nome = data["nome"]
    if "ativo" in data:
        projeto.ativo = data["ativo"]

    return _salvar(projeto)


def definir_projeto_do_aluno(gestor_id: str, aluno_id: str, projeto_id: str | None) -> Aluno:
    """Assign the aluno to a project, or unassign with projeto_id None."""
    gestor = _get_gestor_or_403(
        gestor_id, "Apenas gestores podem definir o projeto do aluno", require_active=True
    )
    aluno_uuid = validate_uuid(aluno_id, "aluno_id")
    # Same lock as excluir_conta, so an account being deleted cannot get a project.
    db.session.execute(select(User.id).where(User.id == aluno_uuid).with_for_update(key_share=True))
    aluno = db.session.get(Aluno, aluno_uuid, populate_existing=True)
    if (
        aluno is None
        or aluno.organizacao_id != gestor.organizacao_id
        or aluno.status == UserStatus.DELETED
    ):
        raise NotFoundError("Aluno não encontrado")

    if projeto_id is None:
        aluno.projeto_id = None
    else:
        projeto = projeto_da_organizacao(gestor.organizacao_id, projeto_id, travar=True)
        if not projeto.ativo:
            raise ValidationError("Projeto desativado não recebe alunos")
        aluno.projeto_id = projeto.id

    db.session.commit()
    return aluno
