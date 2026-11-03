"""Passenger sign-up invite, created by the manager.

The person only becomes a user when they complete the invite. Expired is not a
state: it is a pending invite with `expira_em` in the past.
"""

import uuid

from sqlalchemy.dialects.postgresql import UUID

from .base import db

PENDENTE = "PENDENTE"
CONCLUIDO = "CONCLUIDO"
CANCELADO = "CANCELADO"

ENVIO_PENDENTE = "PENDENTE"
ENVIADO = "ENVIADO"
FALHOU = "FALHOU"


class Convite(db.Model):
    __tablename__ = "convite"
    __table_args__ = (
        # Only one pending invite per e-mail.
        db.Index(
            "uq_convite_email_pendente",
            "email",
            unique=True,
            postgresql_where=db.text("estado = 'PENDENTE'"),
        ),
        db.Index("idx_convite_organizacao", "organizacao_id"),
    )

    id = db.Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    organizacao_id = db.Column(
        UUID(as_uuid=True), db.ForeignKey("organizacao.id", ondelete="CASCADE"), nullable=False
    )
    email = db.Column(db.String(120), nullable=False)

    # Data the manager knew. All optional.
    nome = db.Column(db.String(100))
    cpf = db.Column(db.String(14))
    telefone = db.Column(db.String(20))
    instituicao_id = db.Column(
        UUID(as_uuid=True), db.ForeignKey("instituicao.id", ondelete="SET NULL")
    )

    token = db.Column(db.String(64), unique=True, nullable=False)
    expira_em = db.Column(db.DateTime(timezone=True), nullable=False)
    estado = db.Column(db.String(10), nullable=False, default=PENDENTE)

    # 10-minute PIN, for people who type the e-mail in the app instead of using the
    # link. Only the PIN hash is stored.
    pin_hash = db.Column(db.String(64))
    pin_expira_em = db.Column(db.DateTime(timezone=True))
    pin_tentativas = db.Column(db.Integer, nullable=False, default=0)
    # Errors summed across all the invite's PINs. Reset when the lock ends or the manager resends.
    pin_erros_total = db.Column(db.Integer, nullable=False, default=0, server_default="0")
    # End of the PIN lock after CONVITE_PIN_MAX_ERROS_TOTAL errors; None when not locked.
    pin_bloqueado_ate = db.Column(db.DateTime(timezone=True))
    pin_enviado_em = db.Column(db.DateTime(timezone=True))

    envio_estado = db.Column(db.String(10), nullable=False, default=ENVIO_PENDENTE)
    envio_tentativas = db.Column(db.Integer, nullable=False, default=0)
    enviado_em = db.Column(db.DateTime(timezone=True))

    criado_por_id = db.Column(UUID(as_uuid=True), db.ForeignKey("usuario.id", ondelete="SET NULL"))
    usuario_id = db.Column(UUID(as_uuid=True), db.ForeignKey("usuario.id", ondelete="SET NULL"))

    created_at = db.Column(db.DateTime(timezone=True), server_default=db.func.now(), nullable=False)
    concluido_em = db.Column(db.DateTime(timezone=True))
