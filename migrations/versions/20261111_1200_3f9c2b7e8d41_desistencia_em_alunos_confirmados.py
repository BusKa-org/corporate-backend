"""alunos_confirmados: when a student dropped out of a fixed trip after it left

Revision ID: 3f9c2b7e8d41
Revises: 3f9c2a7e5b14
Create Date: 2026-11-11 12:00:00.000000+00:00
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic
revision: str = "3f9c2b7e8d41"
down_revision: Union[str, None] = "3f9c2a7e5b14"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade database schema."""
    op.add_column(
        "alunos_confirmados",
        sa.Column("desistencia_em", sa.DateTime(timezone=True), nullable=True),
    )


def downgrade() -> None:
    """Downgrade database schema."""
    op.drop_column("alunos_confirmados", "desistencia_em")
