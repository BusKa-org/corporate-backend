"""add convite table (passenger invitations created by the gestor)

Revision ID: f6a7b8c9d0e1
Revises: a1b2c3d4e5f7
Create Date: 2026-09-30 10:00:00.000000+00:00
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql


revision: str = "f6a7b8c9d0e1"
down_revision: Union[str, None] = "a1b2c3d4e5f7"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "convite",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("organizacao_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("email", sa.String(length=120), nullable=False),
        sa.Column("nome", sa.String(length=100), nullable=True),
        sa.Column("cpf", sa.String(length=14), nullable=True),
        sa.Column("telefone", sa.String(length=20), nullable=True),
        sa.Column("instituicao_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("token", sa.String(length=64), nullable=False),
        sa.Column("expira_em", sa.DateTime(timezone=True), nullable=False),
        sa.Column("estado", sa.String(length=10), nullable=False),
        sa.Column("pin_hash", sa.String(length=64), nullable=True),
        sa.Column("pin_expira_em", sa.DateTime(timezone=True), nullable=True),
        sa.Column("pin_tentativas", sa.Integer(), nullable=False),
        sa.Column("pin_enviado_em", sa.DateTime(timezone=True), nullable=True),
        sa.Column("envio_estado", sa.String(length=10), nullable=False),
        sa.Column("envio_tentativas", sa.Integer(), nullable=False),
        sa.Column("enviado_em", sa.DateTime(timezone=True), nullable=True),
        sa.Column("criado_por_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("usuario_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False
        ),
        sa.Column("concluido_em", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(["organizacao_id"], ["organizacao.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["instituicao_id"], ["instituicao.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["criado_por_id"], ["usuario.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["usuario_id"], ["usuario.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("token"),
    )
    op.create_index("idx_convite_organizacao", "convite", ["organizacao_id"])
    op.create_index(
        "uq_convite_email_pendente",
        "convite",
        ["email"],
        unique=True,
        postgresql_where=sa.text("estado = 'PENDENTE'"),
    )


def downgrade() -> None:
    op.drop_index("uq_convite_email_pendente", table_name="convite")
    op.drop_index("idx_convite_organizacao", table_name="convite")
    op.drop_table("convite")
