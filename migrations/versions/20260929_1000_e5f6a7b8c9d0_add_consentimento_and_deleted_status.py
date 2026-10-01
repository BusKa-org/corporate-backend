"""add consentimento table and DELETED user status

Revision ID: e5f6a7b8c9d0
Revises: a1b2c3d4e5f7
Create Date: 2026-09-29 10:00:00.000000+00:00
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql


revision: str = "e5f6a7b8c9d0"
down_revision: Union[str, None] = "a1b2c3d4e5f7"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute("ALTER TYPE user_status ADD VALUE IF NOT EXISTS 'DELETED'")
    op.create_table(
        "consentimento",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("usuario_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("versao", sa.String(length=20), nullable=False),
        sa.Column("acao", sa.String(length=10), nullable=False),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False
        ),
        sa.ForeignKeyConstraint(["usuario_id"], ["usuario.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("idx_consentimento_usuario", "consentimento", ["usuario_id"])
    op.create_table(
        "retencao_legal",
        sa.Column("usuario_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("email", sa.String(length=120), nullable=False),
        sa.Column("cpf", sa.String(length=64), nullable=False),
        sa.Column(
            "excluido_em", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False
        ),
        sa.Column("reter_ate", sa.DateTime(timezone=True), nullable=False),
        sa.Column("anonimizado_em", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(["usuario_id"], ["usuario.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("usuario_id"),
    )


def downgrade() -> None:
    op.drop_table("retencao_legal")
    op.drop_index("idx_consentimento_usuario", table_name="consentimento")
    op.drop_table("consentimento")
    # PostgreSQL does not support removing values from an enum type.
