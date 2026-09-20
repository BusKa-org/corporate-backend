import uuid

from sqlalchemy.dialects.postgresql import UUID

from .base import db
from .enum import UserRole, UserStatus
from .notificacao import Notificacao  # noqa: F401


class User(db.Model):
    __tablename__ = "usuario"
    __table_args__ = (db.Index("idx_usuario_organizacao", "organizacao_id"),)

    id = db.Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    organizacao_id = db.Column(
        UUID(as_uuid=True), db.ForeignKey("organizacao.id", ondelete="CASCADE"), nullable=False
    )
    nome = db.Column(db.String(100), nullable=False)
    email = db.Column(db.String(120), unique=True, nullable=False)
    senha_hash = db.Column(db.String(255), nullable=False)
    telefone = db.Column(db.String(20))
    cpf = db.Column(db.String(14), unique=True, nullable=False)
    receber_notificacoes = db.Column(db.Boolean, default=True, nullable=False)

    fcm_token = db.Column(db.String(255), nullable=True)

    role = db.Column(db.Enum(UserRole, name="user_role"), nullable=False, default=UserRole.ALUNO)
    status = db.Column(
        db.Enum(UserStatus, name="user_status"), nullable=False, default=UserStatus.PENDING_SIGNUP
    )
    signup_completed_at = db.Column(db.DateTime(timezone=True))

    created_at = db.Column(db.DateTime(timezone=True), server_default=db.func.now())
    updated_at = db.Column(
        db.DateTime(timezone=True), server_default=db.func.now(), onupdate=db.func.now()
    )

    notificacoes = db.relationship(
        "Notificacao", backref="usuario", lazy=True, cascade="all, delete-orphan"
    )

    __mapper_args__ = {"polymorphic_identity": UserRole.USER, "polymorphic_on": role}

    @property
    def is_gestor(self):
        return self.role == UserRole.GESTOR


class Motorista(User):
    __tablename__ = "motorista"

    usuario_id = db.Column(
        UUID(as_uuid=True), db.ForeignKey("usuario.id", ondelete="CASCADE"), primary_key=True
    )
    cnh = db.Column(db.String(20), unique=True, nullable=False)

    __mapper_args__ = {
        "polymorphic_identity": UserRole.MOTORISTA,
    }


class Gestor(User):
    __tablename__ = "gestor"

    usuario_id = db.Column(
        UUID(as_uuid=True), db.ForeignKey("usuario.id", ondelete="CASCADE"), primary_key=True
    )

    __mapper_args__ = {
        "polymorphic_identity": UserRole.GESTOR,
    }


# Aluno (BusKá-only) moved to app/models/aluno.py — see that file's docstring.
