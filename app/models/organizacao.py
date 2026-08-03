import uuid

from sqlalchemy.dialects.postgresql import UUID

from .base import db


class Organizacao(db.Model):
    """Tenant: the institution operating a transport service.

    Replaces the municipal `Prefeitura`. `codigo_ibge` is dropped — corporate
    tenants are not municipalities — and `sigla` becomes the stable public key.
    """

    __tablename__ = "organizacao"

    id = db.Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    nome = db.Column(db.String(150), nullable=False)
    sigla = db.Column(db.String(20), nullable=False, unique=True, index=True)
    estado = db.Column(db.String(2), nullable=True)
    ativo = db.Column(db.Boolean, nullable=False, server_default="true", default=True)

    created_at = db.Column(db.DateTime(timezone=True), server_default=db.func.now())

    usuarios = db.relationship("User", backref=db.backref("organizacao", lazy="joined"), lazy=True)
