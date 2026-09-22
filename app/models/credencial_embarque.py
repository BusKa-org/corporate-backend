"""Credencial de embarque (QR dinâmico) — RF-15.

Vincula uma viagem, um aluno e um ponto de embarque a um token opaco. Não
decide quem embarca: representa a decisão de quem gerou a credencial
(buffer e capacidade da rota por demanda, hoje; o mecanismo da rota
definida, quando existir).
"""

import uuid
from datetime import UTC, datetime

from sqlalchemy.dialects.postgresql import UUID

from .base import db


class CredencialEmbarque(db.Model):
    __tablename__ = "credencial_embarque"
    __table_args__ = (
        db.UniqueConstraint(
            "viagem_id",
            "aluno_id",
            "ponto_embarque_id",
            name="uq_credencial_embarque_viagem_aluno_ponto",
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

    token = db.Column(db.String(64), unique=True, nullable=False)
    expires_at = db.Column(db.DateTime(timezone=True), nullable=False)
    usado = db.Column(db.Boolean, default=False, nullable=False)

    created_at = db.Column(db.DateTime(timezone=True), server_default=db.func.now())

    viagem = db.relationship("Viagem")
    aluno = db.relationship("Aluno")
    ponto_embarque = db.relationship("Ponto")

    def is_expired(self) -> bool:
        return datetime.now(UTC) >= self.expires_at
