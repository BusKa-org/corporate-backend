"""Credencial de embarque (QR dinâmico).

Vincula uma viagem, um aluno e um ponto de embarque a um segredo. O app do
aluno deriva desse segredo o código que muda a cada passo (TOTP, RFC 6238) e
desenha o QR `<id>.<codigo>`. Não decide quem embarca: representa a decisão de
quem gerou a credencial (buffer e capacidade da rota por demanda, hoje; o
mecanismo da rota definida, quando existir).
"""

import uuid

from sqlalchemy.dialects.postgresql import UUID

from .base import db


class CredencialEmbarque(db.Model):
    __tablename__ = "credencial_embarque"
    __table_args__ = (
        # No máximo uma credencial ativa por aluno e viagem; a reemitida revoga a anterior.
        db.Index(
            "uq_credencial_embarque_ativa",
            "viagem_id",
            "aluno_id",
            unique=True,
            postgresql_where=db.text("revogada_em IS NULL"),
        ),
    )

    id = db.Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)

    viagem_id = db.Column(
        UUID(as_uuid=True), db.ForeignKey("viagem.id", ondelete="CASCADE"), nullable=False
    )
    aluno_id = db.Column(
        UUID(as_uuid=True), db.ForeignKey("aluno.usuario_id", ondelete="CASCADE"), nullable=False
    )
    ponto_embarque_id = db.Column(UUID(as_uuid=True), db.ForeignKey("ponto.id"), nullable=False)

    # 32 bytes em hexadecimal. Nunca vai para log.
    segredo = db.Column(db.String(64), nullable=False)
    expires_at = db.Column(db.DateTime(timezone=True), nullable=False)
    usado = db.Column(db.Boolean, default=False, nullable=False)

    # RF-17 fluxo secundário 1: a foto não conferiu e o QR não embarca mais ninguém.
    recusada_em = db.Column(db.DateTime(timezone=True), nullable=True)
    motivo_recusa = db.Column(db.String(32), nullable=True)
    # Substituída por outra credencial (o ponto de embarque mudou).
    revogada_em = db.Column(db.DateTime(timezone=True), nullable=True)

    created_at = db.Column(db.DateTime(timezone=True), server_default=db.func.now())

    viagem = db.relationship("Viagem")
    aluno = db.relationship("Aluno")
    ponto_embarque = db.relationship("Ponto")
