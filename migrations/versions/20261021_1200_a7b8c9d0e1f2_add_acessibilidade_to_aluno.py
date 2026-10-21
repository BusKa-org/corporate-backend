"""add acessibilidade to aluno

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
