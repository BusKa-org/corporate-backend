"""LGPD consent record.

One row per event: acceptance or revocation of a terms version. The user's
current state is their latest row. Refusing the terms records nothing.
"""

from sqlalchemy.dialects.postgresql import UUID

from .base import db

ACEITE = "ACEITE"
REVOGACAO = "REVOGACAO"


class Consentimento(db.Model):
    __tablename__ = "consentimento"
    __table_args__ = (db.Index("idx_consentimento_usuario", "usuario_id"),)

    # Sequential integer: the order of a user's events comes from the id.
    id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    usuario_id = db.Column(
        UUID(as_uuid=True), db.ForeignKey("usuario.id", ondelete="CASCADE"), nullable=False
    )
    versao = db.Column(db.String(20), nullable=False)
    acao = db.Column(db.String(10), nullable=False)
    created_at = db.Column(db.DateTime(timezone=True), server_default=db.func.now(), nullable=False)
