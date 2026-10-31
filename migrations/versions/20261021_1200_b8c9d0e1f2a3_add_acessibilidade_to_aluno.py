"""add acessibilidade to aluno

Revision ID: b8c9d0e1f2a3
Revises: b7c1e2f3a4d5
Create Date: 2026-10-21 12:00:00.000000+00:00
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "b8c9d0e1f2a3"
down_revision: Union[str, None] = "b7c1e2f3a4d5"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "aluno",
        sa.Column(
            "necessidades_acessibilidade",
            postgresql.ARRAY(sa.String(30)),
            nullable=False,
            server_default="{}",
        ),
    )
    op.add_column("aluno", sa.Column("observacao_acessibilidade", sa.String(500), nullable=True))


def downgrade() -> None:
    op.drop_column("aluno", "observacao_acessibilidade")
    op.drop_column("aluno", "necessidades_acessibilidade")
