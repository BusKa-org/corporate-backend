import uuid

from sqlalchemy.dialects.postgresql import UUID

from .base import db
from .enum import StatusOcorrencia, TipoOcorrencia


class Ocorrencia(db.Model):
    __tablename__ = "ocorrencia"
    __table_args__ = (
        db.Index("idx_ocorrencia_autor", "autor_id"),
        db.Index("idx_ocorrencia_viagem", "viagem_id"),
        db.Index("idx_ocorrencia_status", "status"),
    )

    id = db.Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)

    autor_id = db.Column(
        UUID(as_uuid=True),
        db.ForeignKey("usuario.id", ondelete="CASCADE"),
        nullable=False,
    )
    viagem_id = db.Column(
        UUID(as_uuid=True),
        db.ForeignKey("viagem.id", ondelete="SET NULL"),
        nullable=True,
    )

    tipo = db.Column(db.Enum(TipoOcorrencia, name="tipo_ocorrencia"), nullable=False)
    descricao = db.Column(db.Text, nullable=True)
    status = db.Column(
        db.Enum(StatusOcorrencia, name="status_ocorrencia"),
        nullable=False,
        default=StatusOcorrencia.ABERTA,
    )

    created_at = db.Column(db.DateTime(timezone=True), server_default=db.func.now())
    updated_at = db.Column(
        db.DateTime(timezone=True),
        server_default=db.func.now(),
        onupdate=db.func.now(),
    )

    autor = db.relationship("User", foreign_keys=[autor_id], lazy="joined")
    viagem = db.relationship("Viagem", foreign_keys=[viagem_id], lazy="select")
