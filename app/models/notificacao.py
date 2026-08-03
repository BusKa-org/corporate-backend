import uuid

from sqlalchemy.dialects.postgresql import UUID

from .base import db


class Notificacao(db.Model):
    __tablename__ = "notificacoes"
    __table_args__ = (db.Index("idx_notificacoes_usuario", "usuario_id"),)

    id = db.Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)

    usuario_id = db.Column(
        UUID(as_uuid=True), db.ForeignKey("usuario.id", ondelete="CASCADE"), nullable=False
    )

    titulo = db.Column(db.String(120), nullable=False)
    mensagem = db.Column(db.Text, nullable=False)
    enviada = db.Column(db.Boolean, server_default="false")
    data_envio = db.Column(db.DateTime(timezone=True))

    created_at = db.Column(db.DateTime(timezone=True), server_default=db.func.now())
    updated_at = db.Column(
        db.DateTime(timezone=True), server_default=db.func.now(), onupdate=db.func.now()
    )
