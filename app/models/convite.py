"""Convite de cadastro de passageiro, criado pelo gestor.

A pessoa só vira usuária quando conclui o convite. Até lá, os dados que o
gestor conhecia ficam aqui. Vencido não é um estado: é um convite pendente
com `expira_em` no passado.
"""

import uuid

from sqlalchemy.dialects.postgresql import UUID

from .base import db

# Estado do convite
PENDENTE = "PENDENTE"
CONCLUIDO = "CONCLUIDO"
CANCELADO = "CANCELADO"

# Estado do envio do e-mail
ENVIO_PENDENTE = "PENDENTE"
ENVIADO = "ENVIADO"
FALHOU = "FALHOU"


class Convite(db.Model):
    __tablename__ = "convite"
    __table_args__ = (
        # Só um convite pendente por e-mail.
        db.Index(
            "uq_convite_email_pendente",
            "email",
            unique=True,
            postgresql_where=db.text("estado = 'PENDENTE'"),
        ),
        db.Index("idx_convite_organizacao", "organizacao_id"),
    )

    id = db.Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    organizacao_id = db.Column(
        UUID(as_uuid=True), db.ForeignKey("organizacao.id", ondelete="CASCADE"), nullable=False
    )
    email = db.Column(db.String(120), nullable=False)

    # Dados que o gestor conhecia. Todos opcionais.
    nome = db.Column(db.String(100))
    cpf = db.Column(db.String(14))
    telefone = db.Column(db.String(20))
    instituicao_id = db.Column(
        UUID(as_uuid=True), db.ForeignKey("instituicao.id", ondelete="SET NULL")
    )

    token = db.Column(db.String(64), unique=True, nullable=False)
    expira_em = db.Column(db.DateTime(timezone=True), nullable=False)
    estado = db.Column(db.String(10), nullable=False, default=PENDENTE)

    envio_estado = db.Column(db.String(10), nullable=False, default=ENVIO_PENDENTE)
    envio_tentativas = db.Column(db.Integer, nullable=False, default=0)
    enviado_em = db.Column(db.DateTime(timezone=True))

    criado_por_id = db.Column(UUID(as_uuid=True), db.ForeignKey("usuario.id", ondelete="SET NULL"))
    usuario_id = db.Column(UUID(as_uuid=True), db.ForeignKey("usuario.id", ondelete="SET NULL"))

    created_at = db.Column(db.DateTime(timezone=True), server_default=db.func.now(), nullable=False)
    concluido_em = db.Column(db.DateTime(timezone=True))
