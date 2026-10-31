import uuid

from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import relationship

from .base import db
from .enum import DiaDaSemana


class JanelaDisponibilidade(db.Model):
    """RF-05: faixa de horário em que o veículo aceita solicitações.

    Fora de qualquer janela ativa o sistema recusa solicitações (RF-10, fluxo
    secundário 2). Cada janela nomeia o motorista responsável, porque é a
    disponibilidade dele que define a operação.
    """

    __tablename__ = "janela_disponibilidade"

    id = db.Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    organizacao_id = db.Column(
        UUID(as_uuid=True), db.ForeignKey("organizacao.id", ondelete="CASCADE"), nullable=False
    )
    rota_id = db.Column(
        UUID(as_uuid=True), db.ForeignKey("rota.id", ondelete="CASCADE"), nullable=False
    )
    motorista_id = db.Column(
        UUID(as_uuid=True),
        db.ForeignKey("motorista.usuario_id", ondelete="RESTRICT"),
        nullable=False,
    )
    veiculo_id = db.Column(
        UUID(as_uuid=True), db.ForeignKey("onibus.id", ondelete="RESTRICT"), nullable=True
    )

    dia = db.Column(db.Enum(DiaDaSemana, name="dia_da_semana"), nullable=False)
    hora_inicio = db.Column(db.Time, nullable=False)
    hora_fim = db.Column(db.Time, nullable=False)

    # RF-11: o N da contagem regressiva, configurável pelo gestor por janela.
    buffer_minutos = db.Column(db.Integer, nullable=False, server_default="5", default=5)

    ativo = db.Column(db.Boolean, nullable=False, server_default="true", default=True)

    created_at = db.Column(db.DateTime(timezone=True), server_default=db.func.now())
    updated_at = db.Column(
        db.DateTime(timezone=True), server_default=db.func.now(), onupdate=db.func.now()
    )

    organizacao = relationship("Organizacao")
    rota = relationship("Rota")
    motorista = relationship("Motorista")
    veiculo = relationship("Onibus")

    __table_args__ = (
        db.CheckConstraint("hora_fim > hora_inicio", name="ck_janela_ordem_horas"),
        db.CheckConstraint("buffer_minutos > 0", name="ck_janela_buffer_positivo"),
        db.Index("idx_janela_org_dia", "organizacao_id", "dia"),
    )
