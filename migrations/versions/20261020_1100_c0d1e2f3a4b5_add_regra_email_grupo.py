"""add regra_email_grupo (email domains that suggest a group on the invitation)

Revision ID: c0d1e2f3a4b5
Revises: b9c0d1e2f3a4
Create Date: 2026-10-20 11:00:00.000000+00:00
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql


revision: str = "c0d1e2f3a4b5"
down_revision: Union[str, None] = "b9c0d1e2f3a4"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "regra_email_grupo",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("grupo_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("dominio", sa.String(length=255), nullable=False),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False
        ),
        sa.ForeignKeyConstraint(["grupo_id"], ["grupo.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("grupo_id", "dominio", name="uq_regra_email_grupo_dominio"),
    )
    op.create_index("idx_regra_email_grupo_dominio", "regra_email_grupo", ["dominio"])


def downgrade() -> None:
    op.drop_index("idx_regra_email_grupo_dominio", table_name="regra_email_grupo")
    op.drop_table("regra_email_grupo")
