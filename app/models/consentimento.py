"""Registro de consentimento LGPD.

Uma linha por evento: aceite ou revogação de uma versão do termo. O estado
atual do usuário é a linha mais recente dele. Recusar o termo não grava nada.
"""

from sqlalchemy.dialects.postgresql import UUID

from .base import db

ACEITE = "ACEITE"
REVOGACAO = "REVOGACAO"


class Consentimento(db.Model):
    __tablename__ = "consentimento"
    __table_args__ = (db.Index("idx_consentimento_usuario", "usuario_id"),)

    # Inteiro sequencial: a ordem dos eventos do usuário sai do id.
    id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    usuario_id = db.Column(
        UUID(as_uuid=True), db.ForeignKey("usuario.id", ondelete="CASCADE"), nullable=False
    )
    versao = db.Column(db.String(20), nullable=False)
    acao = db.Column(db.String(10), nullable=False)
    created_at = db.Column(db.DateTime(timezone=True), server_default=db.func.now(), nullable=False)
