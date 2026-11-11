from sqlalchemy.dialects.postgresql import UUID

from .base import db


class ParametrosOperacao(db.Model):
    """On-demand operation parameters set by the organization's manager.

    No row means the defaults from Settings (OPERACAO_*_PADRAO).
    """

    __tablename__ = "parametros_operacao"

    organizacao_id = db.Column(
        UUID(as_uuid=True),
        db.ForeignKey("organizacao.id", ondelete="CASCADE"),
        primary_key=True,
    )
    minimo_alunos = db.Column(db.Integer, nullable=False)
    pausa_entre_viagens_minutos = db.Column(db.Integer, nullable=False)
    # shortcut: stored only, not enforced; enforce once the gestor defines what lead time means
    # for on-demand trips.
    antecedencia_motorista_minutos = db.Column(db.Integer, nullable=False)
    updated_at = db.Column(
        db.DateTime(timezone=True), server_default=db.func.now(), onupdate=db.func.now()
    )
