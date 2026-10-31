"""add horario de trabalho and descanso_ate to motorista

Revision ID: a7b8c9d0e1f2
Revises: e5f6a7b8c9d0
Create Date: 2026-10-21 12:00:00.000000+00:00
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "a7b8c9d0e1f2"
down_revision: Union[str, None] = "e5f6a7b8c9d0"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("motorista", sa.Column("horario_inicio", sa.Time(), nullable=True))
    op.add_column("motorista", sa.Column("horario_fim", sa.Time(), nullable=True))
    op.add_column(
        "motorista",
        sa.Column("dias_trabalho", postgresql.ARRAY(sa.String(length=3)), nullable=True),
    )

    op.add_column("motorista", sa.Column("descanso_ate", sa.DateTime(timezone=True), nullable=True))


def downgrade() -> None:
    op.drop_column("motorista", "descanso_ate")
    op.drop_column("motorista", "dias_trabalho")
    op.drop_column("motorista", "horario_fim")
    op.drop_column("motorista", "horario_inicio")
