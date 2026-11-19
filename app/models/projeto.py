import uuid

from sqlalchemy.dialects.postgresql import UUID

from .base import db


class Projeto(db.Model):
    """Project an aluno belongs to inside the organization (e.g. a company in the tech park)."""

    __tablename__ = "projeto"

    id = db.Column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
        server_default=db.text("uuid_generate_v4()"),
    )
    organizacao_id = db.Column(
        UUID(as_uuid=True),
        db.ForeignKey("organizacao.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    nome = db.Column(db.String(100), nullable=False)
    # Deactivated instead of deleted, so alunos keep the link for history.
    ativo = db.Column(db.Boolean, nullable=False, default=True, server_default=db.true())
    created_at = db.Column(db.DateTime(timezone=True), server_default=db.func.now())

    __table_args__ = (
        # "Projeto A" and "projeto a" count as the same name.
        db.Index(
            "uq_projeto_organizacao_nome",
            "organizacao_id",
            db.func.lower(nome),
            unique=True,
        ),
    )
