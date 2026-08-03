import uuid
from datetime import UTC, datetime

from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import relationship

from .base import db


class TelemetriaVeiculo(db.Model):
    """RF-22: série temporal de telemetria da bateria do veículo elétrico.

    Distinta de `TelemetriaViagem`, que é o rastro de GPS. As amostras chegam
    por um adaptador de veículo que vive no repositório do cliente — aqui só
    existe a ingestão e o armazenamento.

    ponytail: série temporal em tabela Postgres comum. Basta para um veículo;
    se virarem muitos, particionar por mês ou migrar para TimescaleDB.
    """

    __tablename__ = "telemetria_veiculo"

    id = db.Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    veiculo_id = db.Column(
        UUID(as_uuid=True),
        db.ForeignKey("onibus.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    # Nulo quando a amostra chega com o veículo fora de operação.
    viagem_id = db.Column(
        UUID(as_uuid=True), db.ForeignKey("viagem.id", ondelete="SET NULL"), nullable=True
    )

    timestamp = db.Column(
        db.DateTime(timezone=True), default=lambda: datetime.now(UTC), nullable=False
    )

    nivel_bateria = db.Column(db.Numeric(5, 2), nullable=True)  # % de carga
    consumo_kwh = db.Column(db.Numeric(10, 3), nullable=True)
    autonomia_km = db.Column(db.Numeric(10, 2), nullable=True)
    odometro_km = db.Column(db.Numeric(12, 2), nullable=True)
    saude_bateria = db.Column(db.Numeric(5, 2), nullable=True)  # SOH %, se exposto

    veiculo = relationship("Onibus")
    viagem = relationship("Viagem")

    __table_args__ = (
        db.Index("idx_telemetria_veiculo_ts", "veiculo_id", "timestamp"),
        db.CheckConstraint(
            "nivel_bateria IS NULL OR (nivel_bateria >= 0 AND nivel_bateria <= 100)",
            name="ck_telemetria_nivel_bateria",
        ),
    )
