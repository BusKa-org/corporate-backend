"""rota.ligada: gestor switch to turn a route on and off

Separate from rota.ativa, which marks a removed route kept only for its trip history.

Revision ID: 8b1d4e6f2a93
Revises: 3f9c2b7e8d41
Create Date: 2026-11-18 12:00:00.000000+00:00
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic
revision: str = "8b1d4e6f2a93"
down_revision: Union[str, None] = "3f9c2b7e8d41"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade database schema."""
    op.add_column(
        "rota",
        sa.Column("ligada", sa.Boolean(), nullable=False, server_default=sa.true()),
    )


def downgrade() -> None:
    """Downgrade database schema."""
    op.drop_column("rota", "ligada")
