"""drop_gestor_columns

Revision ID: a1b2c3d4e5f6
Revises: fba2f1a067db
Create Date: 2026-04-08 02:31:00.000000+00:00
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic
revision: str = "a1b2c3d4e5f6"
down_revision: Union[str, None] = "fba2f1a067db"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade database schema."""
    op.drop_column("gestor", "matricula")
    op.drop_column("gestor", "salario")


def downgrade() -> None:
    """Downgrade database schema."""
    op.add_column("gestor", sa.Column("salario", sa.NUMERIC(precision=10, scale=2), nullable=True))
    op.add_column("gestor", sa.Column("matricula", sa.VARCHAR(length=50), nullable=True))
