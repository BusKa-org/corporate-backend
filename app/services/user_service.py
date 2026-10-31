"""User service - CRUD operations, driver creation, password management."""

import logging
from datetime import UTC, datetime
from typing import Any, cast

from sqlalchemy.orm import with_polymorphic
from werkzeug.security import check_password_hash, generate_password_hash

from app.core.exceptions import (
    AppError,
    ConflictError,
    ForbiddenError,
    NotFoundError,
    UnauthorizedError,
    ValidationError,
)
from app.models.base import db
from app.models.enum import UserRole, UserStatus
from app.models.user import Gestor, Motorista, User
from app.services.viagens_service import motoristas_em_viagem, status_motorista
from app.utils import audit_logger, validate_cpf, validate_email, validate_password, validate_uuid

logger = logging.getLogger(__name__)


# Helper functions
def _require_active(user: User) -> None:
    if user.status != UserStatus.ACTIVE:
        raise ForbiddenError("Cadastro precisa ser finalizado antes de usar o app")


def _get_user_or_404(user_id: str) -> User:
    """Get user by ID or raise NotFoundError."""
    validate_uuid(user_id, "User ID")
    user = db.session.get(User, user_id)
    if not user:
        raise NotFoundError("Usuário não encontrado")
    return user


def _get_gestor_or_403(
    user_id: str, message: str = "Apenas gestores podem executar esta ação"
) -> Gestor:
    user = _get_user_or_404(user_id)
    if user.role != UserRole.GESTOR:
        raise ForbiddenError(message)
    return cast(Gestor, user)


def _preencher_status_motoristas(users: list[User]) -> None:
    """Compute each driver's state for the response, with one query for the whole list."""
    motorista_ids = []
    for user in users:
        if isinstance(user, Motorista):
            motorista_ids.append(user.id)
    if not motorista_ids:
        return
    em_viagem = motoristas_em_viagem(motorista_ids)
    agora = datetime.now(UTC)
    for user in users:
        if isinstance(user, Motorista):
            user.status_motorista = status_motorista(user, agora, user.id in em_viagem)


def get_all_users(current_user_id: str) -> list[User]:
    """List all users in the same organizacao (gestor only)."""
    gestor = _get_gestor_or_403(current_user_id, "Apenas gestores podem listar usuários")
    # with_polymorphic carrega as colunas de cada subtipo na mesma query (sem N+1)
    todos = with_polymorphic(User, "*")
    users = db.session.query(todos).filter(todos.organizacao_id == gestor.organizacao_id).all()
    _preencher_status_motoristas(users)
    return users


def get_user_by_id(user_id: str, current_user_id: str | None = None) -> User:
    """
    Get user by ID with tenant isolation.
    Users can view themselves, gestores can view users in their organizacao.
    """
    user = _get_user_or_404(user_id)

    # Skip authorization for internal use
    if current_user_id is None:
        _preencher_status_motoristas([user])
        return user

    current_user = _get_user_or_404(current_user_id)

    # Allow self-access
    if str(user_id) == str(current_user_id):
        _preencher_status_motoristas([user])
        return user

    # Allow gestor access within same organizacao
    if current_user.role == UserRole.GESTOR and user.organizacao_id == current_user.organizacao_id:
        _preencher_status_motoristas([user])
        return user

    # Log unauthorized access attempt
    audit_logger.log_security_event(
        event_type="unauthorized_user_access",
        severity="medium",
        user_id=current_user_id,
        details={"target_user_id": user_id},
    )
    raise ForbiddenError("Sem permissão para visualizar este usuário")


def update_user(user_id: str, data: dict[str, Any]) -> User:
    """Update user data (nome, email, password, telefone)."""
    user = _get_user_or_404(user_id)

    if nome := data.get("nome"):
        user.nome = nome.strip()

    if email := data.get("email"):
        email_validated = validate_email(email)
        if existing := db.session.query(User).filter_by(email=email_validated).first():
            if existing.id != user.id:
                raise ConflictError("Email já está em uso")
        user.email = email_validated

    if password := data.get("password"):
        password = validate_password(password)
        user.senha_hash = generate_password_hash(password)

    if telefone := data.get("telefone"):
        user.telefone = telefone.strip()

    try:
        db.session.commit()
        return user
    except (ValidationError, ConflictError):
        raise
    except Exception as e:
        db.session.rollback()
        logger.error(f"Error updating user: {e}", exc_info=True)
        raise AppError(f"Erro ao atualizar usuário: {str(e)}", 500)


def _aplicar_jornada(motorista: Motorista, data: dict[str, Any]) -> None:
    """Copy working-hours fields present in `data` onto the driver and validate them."""
    if "horario_inicio" in data:
        motorista.horario_inicio = data["horario_inicio"]
    if "horario_fim" in data:
        motorista.horario_fim = data["horario_fim"]
    if "dias_trabalho" in data:
        dias = data["dias_trabalho"]
        if dias is None:
            motorista.dias_trabalho = None
        else:
            valores: list[str] = []
            for dia in dias:
                if dia.value not in valores:
                    valores.append(dia.value)
            motorista.dias_trabalho = valores

    inicio = motorista.horario_inicio
    fim = motorista.horario_fim
    if (inicio is None) != (fim is None):
        raise ValidationError("Informe o início e o fim do horário de trabalho")
    if inicio is not None and inicio == fim:
        raise ValidationError("Início e fim do horário de trabalho não podem ser iguais")


def create_motorista(gestor_id: str, data: dict[str, Any]) -> Motorista:
    """Create a new driver (gestor only)."""
    gestor = _get_gestor_or_403(gestor_id, "Apenas gestores podem cadastrar motoristas")

    email = validate_email(data.get("email", ""))
    cpf_clean = validate_cpf(data.get("cpf", ""))

    if db.session.query(User).filter((User.email == email) | (User.cpf == cpf_clean)).first():
        raise ConflictError("Email ou CPF já cadastrado")

    if not (cnh := data.get("cnh", "").strip()):
        raise ValidationError("CNH é obrigatória para motoristas")

    if db.session.query(Motorista).filter_by(cnh=cnh).first():
        raise ConflictError("CNH já cadastrada")

    password = validate_password(data.get("password", ""))

    try:
        new_motorista = Motorista(
            organizacao_id=gestor.organizacao_id,
            nome=data["nome"],
            email=email,
            senha_hash=generate_password_hash(password),
            cpf=cpf_clean,
            telefone=data.get("telefone", "").strip(),
            role=UserRole.MOTORISTA,
            cnh=cnh,
        )
        _aplicar_jornada(new_motorista, data)

        db.session.add(new_motorista)
        db.session.commit()
        _preencher_status_motoristas([new_motorista])
        return new_motorista

    except (ValidationError, ConflictError, ForbiddenError):
        raise
    except Exception as e:
        db.session.rollback()
        logger.error(f"Error creating motorista: {e}", exc_info=True)
        raise AppError(f"Erro ao criar motorista: {str(e)}", 500)


def update_motorista(gestor_id: str, motorista_id: str, data: dict[str, Any]) -> Motorista:
    """Gestor updates a driver of the same organizacao, including working hours."""
    gestor = _get_gestor_or_403(gestor_id, "Apenas gestores podem editar motoristas")

    user = _get_user_or_404(motorista_id)
    if user.role != UserRole.MOTORISTA:
        raise NotFoundError("Motorista não encontrado")
    if user.organizacao_id != gestor.organizacao_id:
        raise ForbiddenError("Proibido editar motoristas de outra organização")
    motorista = cast(Motorista, user)

    if nome := data.get("nome"):
        motorista.nome = nome
    if telefone := data.get("telefone"):
        motorista.telefone = telefone
    if cnh := data.get("cnh"):
        existing = db.session.query(Motorista).filter_by(cnh=cnh).first()
        if existing and existing.id != motorista.id:
            raise ConflictError("CNH já cadastrada para outro motorista", field="cnh")
        motorista.cnh = cnh

    try:
        _aplicar_jornada(motorista, data)
    except ValidationError:
        db.session.rollback()
        raise

    db.session.commit()
    audit_logger.log_user_action(
        action="update_motorista",
        user_id=gestor_id,
        resource_type="motorista",
        resource_id=motorista_id,
    )
    _preencher_status_motoristas([motorista])
    return motorista


def change_password(user_id: str, data: dict[str, Any]) -> None:
    """Change user password (requires current password verification)."""
    user = _get_user_or_404(user_id)

    current_password = data.get("current_password")
    new_password = data.get("new_password")

    if not current_password or not new_password:
        raise ValidationError("Senha atual e nova senha são obrigatórias")

    new_password = validate_password(new_password, "Nova senha")

    if new_password == current_password:
        raise ValidationError("Nova senha deve ser diferente da senha atual")

    # Verify current password and log failed attempts
    if not check_password_hash(user.senha_hash, current_password):
        audit_logger.log_security_event(
            event_type="failed_password_change",
            severity="medium",
            user_id=user_id,
            details={"reason": "incorrect_current_password"},
        )
        raise UnauthorizedError("A senha atual está incorreta")

    try:
        user.senha_hash = generate_password_hash(new_password)
        db.session.commit()

        # Log successful password change
        audit_logger.log_user_action(
            action="change_password",
            user_id=user_id,
            resource_type="user",
            resource_id=user_id,
        )

    except Exception as e:
        db.session.rollback()
        logger.error(f"Error changing password: {e}", exc_info=True)
        raise AppError(f"Erro ao atualizar senha: {str(e)}", 500)


def get_motoristas_by_municipio(gestor_id: str):
    gestor = _get_user_or_404(gestor_id)

    # Consulta Motorista direto: via User, as colunas de motorista vinham uma query por linha
    motoristas = (
        db.session.query(Motorista).filter(Motorista.organizacao_id == gestor.organizacao_id).all()
    )
    _preencher_status_motoristas(motoristas)

    return motoristas


def update_profile(user_id: str, data: dict[str, Any]) -> User:
    """
    Update own profile fields (nome, telefone, receber_notificacoes).
    Motoristas may also update cnh.

    Raises: NotFoundError, ConflictError, ValidationError, AppError
    """
    user = _get_user_or_404(user_id)

    if nome := data.get("nome"):
        user.nome = nome.strip()

    if telefone := data.get("telefone"):
        user.telefone = telefone.strip()

    if "receber_notificacoes" in data:
        user.receber_notificacoes = bool(data["receber_notificacoes"])

    if user.role == UserRole.MOTORISTA and (cnh := data.get("cnh")):
        cnh = cnh.strip()
        existing = db.session.query(Motorista).filter_by(cnh=cnh).first()
        if existing and str(existing.id) != str(user_id):
            raise ConflictError("CNH já cadastrada para outro motorista", field="cnh")
        cast(Motorista, user).cnh = cnh

    try:
        db.session.commit()
        audit_logger.log_user_action(
            action="update_profile",
            user_id=user_id,
            resource_type="user",
            resource_id=user_id,
        )
        _preencher_status_motoristas([user])
        return user
    except Exception as e:
        db.session.rollback()
        logger.error(f"Error updating profile: {e}", exc_info=True)
        raise AppError(f"Erro ao atualizar perfil: {str(e)}", 500)


def delete_motorista(gestor_id: str, motorista_id: str) -> None:
    """
    Remove a motorista account (gestor only, same organizacao).

    Raises: ForbiddenError, NotFoundError, AppError
    """
    gestor = _get_gestor_or_403(gestor_id, "Apenas gestores podem remover motoristas")

    motorista = db.session.get(User, motorista_id)
    if not motorista or motorista.role != UserRole.MOTORISTA:
        raise NotFoundError("Motorista não encontrado")

    if motorista.organizacao_id != gestor.organizacao_id:
        raise ForbiddenError("Proibido remover motoristas de outra organização")

    try:
        db.session.delete(motorista)
        db.session.commit()
        audit_logger.log_user_action(
            action="delete_motorista",
            user_id=gestor_id,
            resource_type="motorista",
            resource_id=motorista_id,
        )
    except Exception as e:
        db.session.rollback()
        logger.error(f"Error deleting motorista: {e}", exc_info=True)
        raise AppError(
            "Não é possível remover este motorista pois ele possui viagens vinculadas", 400
        )


def update_fcm_token(user_id: str, data: dict[str, Any]) -> None:
    """Update the FCM token for a user."""
    user = _get_user_or_404(user_id)
    user.fcm_token = data.get("fcm_token")
    db.session.commit()
