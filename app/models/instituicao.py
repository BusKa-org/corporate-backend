"""Instituicao — BusKá-only concept, not part of the shared core.

PaqTcPB has no notion of "instituição" the way municipal school transport
does (a school sourced from INEP/EMEC catalogs). This file existed inside
`geo.py` until the split documented in ARQUITETURA_REPOSITORIOS.md §2/§4:
`Ponto` and `Endereco` are core primitives every client needs, `Instituicao`
is BusKá-specific and belongs with the rest of the school-transport module
when that extraction happens.
"""

import enum
import uuid

from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import relationship

from .base import db


class TipoInstituicao(enum.Enum):
    INSTITUTO_FEDERAL = "Instituto Federal"
    UNIVERSIDADE_PUBLICA = "Universidade Pública"
    UNIVERSIDADE_PRIVADA = "Universidade Privada"
    ESCOLA_PUBLICA = "Escola Pública"
    ESCOLA_PRIVADA = "Escola Privada"
    ESCOLA_COMUNITARIA = "Escola Comunitária"


class Instituicao(db.Model):
    __tablename__ = "instituicao"

    id = db.Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)

    fonte = db.Column(db.String(20), nullable=False)  # "EMEC" | "INEP" | "MANUAL"
    codigo_externo = db.Column(db.String(30), nullable=False)

    nome = db.Column(db.String(200), nullable=False)
    sigla = db.Column(db.String(40))
    cnpj = db.Column(db.String(20))

    tipo = db.Column(
        db.Enum(TipoInstituicao, name="tipo_instituicao"),
        nullable=False,
    )

    uf = db.Column(db.String(2), nullable=False, index=True)

    organizacao_id = db.Column(
        UUID(as_uuid=True),
        db.ForeignKey("organizacao.id"),
        nullable=False,
        index=True,
    )

    organizacao = db.relationship("Organizacao", lazy="joined")

    situacao = db.Column(db.String(80))
    categoria_administrativa = db.Column(db.String(80))
    organizacao_academica = db.Column(db.String(80))

    ponto_id = db.Column(
        UUID(as_uuid=True),
        db.ForeignKey("ponto.id", ondelete="CASCADE"),
        nullable=True,
    )

    ponto = relationship("Ponto", back_populates="instituicao")

    __table_args__ = (
        db.UniqueConstraint(
            "fonte",
            "codigo_externo",
            name="uq_instituicao_fonte_codigo_externo",
        ),
    )
