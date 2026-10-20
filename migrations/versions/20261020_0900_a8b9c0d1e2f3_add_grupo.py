"""add grupo, grupo_membro and convite_grupo

Revision ID: a8b9c0d1e2f3
Revises: e5f6a7b8c9d0
Create Date: 2026-10-20 09:00:00.000000+00:00
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql


revision: str = "a8b9c0d1e2f3"
down_revision: Union[str, None] = "e5f6a7b8c9d0"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "grupo",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("organizacao_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("nome", sa.String(length=100), nullable=False),
        sa.Column("descricao", sa.String(length=255), nullable=True),
        sa.Column("data_inicio", sa.Date(), nullable=True),
        sa.Column("data_fim", sa.Date(), nullable=True),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False
        ),
        sa.ForeignKeyConstraint(["organizacao_id"], ["organizacao.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("organizacao_id", "nome", name="uq_grupo_organizacao_nome"),
    )
    op.create_table(
        "grupo_membro",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("grupo_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("usuario_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("data_inicio", sa.Date(), nullable=False),
        sa.Column("data_fim", sa.Date(), nullable=True),
        sa.ForeignKeyConstraint(["grupo_id"], ["grupo.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["usuario_id"], ["aluno.usuario_id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("idx_grupo_membro_usuario", "grupo_membro", ["usuario_id"])
    op.create_index(
        "uq_grupo_membro_aberto",
        "grupo_membro",
        ["grupo_id", "usuario_id"],
        unique=True,
        postgresql_where=sa.text("data_fim IS NULL"),
    )
    op.create_table(
        "convite_grupo",
        sa.Column("convite_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("grupo_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.ForeignKeyConstraint(["convite_id"], ["convite.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["grupo_id"], ["grupo.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("convite_id", "grupo_id"),
    )


def downgrade() -> None:
    op.drop_table("convite_grupo")
    op.drop_index("uq_grupo_membro_aberto", table_name="grupo_membro")
    op.drop_index("idx_grupo_membro_usuario", table_name="grupo_membro")
    op.drop_table("grupo_membro")
    op.drop_table("grupo")
