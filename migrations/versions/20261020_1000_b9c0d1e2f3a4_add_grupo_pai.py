"""add grupo.grupo_pai_id (subgroups, one level)

Revision ID: b9c0d1e2f3a4
Revises: a8b9c0d1e2f3
Create Date: 2026-10-20 10:00:00.000000+00:00
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql


revision: str = "b9c0d1e2f3a4"
down_revision: Union[str, None] = "a8b9c0d1e2f3"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("grupo", sa.Column("grupo_pai_id", postgresql.UUID(as_uuid=True), nullable=True))
    op.create_foreign_key(
        "fk_grupo_grupo_pai", "grupo", "grupo", ["grupo_pai_id"], ["id"], ondelete="RESTRICT"
    )


def downgrade() -> None:
    op.drop_constraint("fk_grupo_grupo_pai", "grupo", type_="foreignkey")
    op.drop_column("grupo", "grupo_pai_id")
