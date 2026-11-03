"""Data kept after account deletion, by legal obligation.

Keeps only what is needed to contact and locate the person in a possible
inquiry (audit, lawsuit). No endpoint reads this table. When `reter_ate`
passes, a quarterly task replaces e-mail and CPF with irreversible hashes and
sets `anonimizado_em`. The row is never deleted.
"""

from sqlalchemy.dialects.postgresql import UUID

from .base import db


class RetencaoLegal(db.Model):
    __tablename__ = "retencao_legal"

    usuario_id = db.Column(
        UUID(as_uuid=True), db.ForeignKey("usuario.id", ondelete="CASCADE"), primary_key=True
    )
    email = db.Column(db.String(120), nullable=False)
    # 64 characters: after anonymization it holds a hex SHA-256 hash.
    cpf = db.Column(db.String(64), nullable=False)
    excluido_em = db.Column(
        db.DateTime(timezone=True), server_default=db.func.now(), nullable=False
    )
    reter_ate = db.Column(db.DateTime(timezone=True), nullable=False)
    anonimizado_em = db.Column(db.DateTime(timezone=True))
