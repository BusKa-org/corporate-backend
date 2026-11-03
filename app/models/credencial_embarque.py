"""Boarding credential (dynamic QR).

Links a trip, a student and a boarding stop to a secret. The student app
derives from it the code that changes every step (TOTP, RFC 6238) and draws
the QR `<id>.<codigo>`. It does not decide who boards: it records the decision
of whoever issued the credential.
"""

import uuid

from sqlalchemy.dialects.postgresql import UUID

from .base import db


class CredencialEmbarque(db.Model):
    __tablename__ = "credencial_embarque"
    __table_args__ = (
        # At most one active credential per student and trip; reissuing revokes the previous one.
        db.Index(
            "uq_credencial_embarque_ativa",
            "viagem_id",
            "aluno_id",
            unique=True,
            postgresql_where=db.text("revogada_em IS NULL"),
        ),
    )

    id = db.Column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
        server_default=db.text("uuid_generate_v4()"),
    )

    viagem_id = db.Column(
        UUID(as_uuid=True), db.ForeignKey("viagem.id", ondelete="CASCADE"), nullable=False
    )
    aluno_id = db.Column(
        UUID(as_uuid=True), db.ForeignKey("aluno.usuario_id", ondelete="CASCADE"), nullable=False
    )
    ponto_embarque_id = db.Column(UUID(as_uuid=True), db.ForeignKey("ponto.id"), nullable=False)

    # 32 bytes in hex. Never logged.
    segredo = db.Column(db.String(64), nullable=False)
    expires_at = db.Column(db.DateTime(timezone=True), nullable=False)
    usado = db.Column(db.Boolean, default=False, nullable=False, server_default=db.false())

    # RF-17 secondary flow 1: the photo did not match and the QR boards no one else.
    recusada_em = db.Column(db.DateTime(timezone=True), nullable=True)
    motivo_recusa = db.Column(db.String(32), nullable=True)
    # Replaced by another credential (the boarding stop changed).
    revogada_em = db.Column(db.DateTime(timezone=True), nullable=True)

    created_at = db.Column(db.DateTime(timezone=True), server_default=db.func.now())

    viagem = db.relationship("Viagem")
    aluno = db.relationship("Aluno")
    ponto_embarque = db.relationship("Ponto")
