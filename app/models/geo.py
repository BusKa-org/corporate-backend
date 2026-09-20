import uuid

from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import relationship

from .base import db


class Ponto(db.Model):
    __tablename__ = "ponto"

    id = db.Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    organizacao_id = db.Column(
        UUID(as_uuid=True), db.ForeignKey("organizacao.id", ondelete="CASCADE"), nullable=False
    )
    latitude = db.Column(db.Numeric(10, 8), nullable=False)
    longitude = db.Column(db.Numeric(11, 8), nullable=False)
    apelido = db.Column(db.String(100))
    # Note: 'geom' column is a generated column in PostgreSQL, managed by DB

    created_at = db.Column(db.DateTime(timezone=True), server_default=db.func.now())

    endereco = relationship(
        "Endereco", back_populates="ponto", uselist=False, cascade="all, delete-orphan"
    )
    instituicao = relationship(
        "Instituicao", back_populates="ponto", uselist=False, cascade="all, delete-orphan"
    )

    def to_dict(self):
        return {
            "id": str(self.id),
            "apelido": self.apelido,
            "latitude": float(self.latitude),
            "longitude": float(self.longitude),
            # Optional: return extra data if available
            "endereco": self.endereco.logradouro if self.endereco else None,
            "instituicao": self.instituicao.nome if self.instituicao else None,
        }


class Endereco(db.Model):
    __tablename__ = "endereco"

    id = db.Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    logradouro = db.Column(db.String(150))
    numero = db.Column(db.String(20))
    bairro = db.Column(db.String(100))
    cidade = db.Column(db.String(100))
    cep = db.Column(db.String(10))

    ponto_id = db.Column(
        UUID(as_uuid=True),
        db.ForeignKey("ponto.id", ondelete="SET NULL"),
        nullable=True,  # Matches DB: ON DELETE SET NULL
    )

    ponto = relationship("Ponto", back_populates="endereco")


# Instituicao (BusKá-only) moved to app/models/instituicao.py — see that file's
# docstring. Ponto.instituicao above resolves it by name at mapper-configure
# time, same as before; app/models/__init__.py imports it so it registers.
