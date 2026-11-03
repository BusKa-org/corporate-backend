import uuid

from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import relationship

from .base import db
from .enum import DiaDaSemana


class Onibus(db.Model):
    __tablename__ = "onibus"

    id = db.Column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
        server_default=db.text("uuid_generate_v4()"),
    )

    organizacao_id = db.Column(
        UUID(as_uuid=True), db.ForeignKey("organizacao.id", ondelete="CASCADE"), nullable=False
    )

    placa = db.Column(db.String(10), unique=True, nullable=False)
    modelo = db.Column(db.String(50))
    capacidade = db.Column(db.Integer, nullable=False)

    created_at = db.Column(db.DateTime(timezone=True), server_default=db.func.now())

    def __repr__(self):
        return f"<Onibus {self.placa}>"


class JanelaDisponibilidade(db.Model):
    """Time when the vehicle operates on demand, with the assigned driver (RF-05).

    hora_inicio/hora_fim are the organization's local time (Settings.TIMEZONE).
    The interval is [hora_inicio, hora_fim): adjacent windows do not overlap.
    """

    __tablename__ = "janela_disponibilidade"
    __table_args__ = (
        db.CheckConstraint("hora_fim > hora_inicio", name="ck_janela_horario"),
        db.Index("idx_janela_onibus_dia", "onibus_id", "dia"),
    )

    id = db.Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    onibus_id = db.Column(
        UUID(as_uuid=True), db.ForeignKey("onibus.id", ondelete="CASCADE"), nullable=False
    )
    motorista_id = db.Column(
        UUID(as_uuid=True),
        db.ForeignKey("motorista.usuario_id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    dia = db.Column(db.Enum(DiaDaSemana, name="dia_da_semana"), nullable=False)
    hora_inicio = db.Column(db.Time, nullable=False)
    hora_fim = db.Column(db.Time, nullable=False)

    created_at = db.Column(db.DateTime(timezone=True), server_default=db.func.now())

    onibus = relationship("Onibus")
    motorista = relationship("Motorista")
