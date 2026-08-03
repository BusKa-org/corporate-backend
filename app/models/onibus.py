import uuid

from sqlalchemy.dialects.postgresql import UUID

from .base import db


class Onibus(db.Model):
    __tablename__ = "onibus"

    id = db.Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)

    prefeitura_id = db.Column(
        UUID(as_uuid=True), db.ForeignKey("prefeitura.id", ondelete="CASCADE"), nullable=False
    )

    placa = db.Column(db.String(10), unique=True, nullable=False)
    modelo = db.Column(db.String(50))
    capacidade = db.Column(db.Integer, nullable=False)

    created_at = db.Column(db.DateTime(timezone=True), server_default=db.func.now())

    def __repr__(self):
        return f"<Onibus {self.placa}>"
