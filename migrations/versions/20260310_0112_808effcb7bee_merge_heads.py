"""merge heads

Revision ID: 808effcb7bee
Revises: 20260305_reset, a6920921396a
Create Date: 2026-03-10 01:12:48.117184+00:00
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic
revision: str = "808effcb7bee"
down_revision: Union[str, None] = ("20260305_reset", "a6920921396a")
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade database schema."""
    pass


def downgrade() -> None:
    """Downgrade database schema."""
    pass
