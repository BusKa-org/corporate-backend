"""merge heads

Revision ID: ac7627fc4b56
Revises: a6920921396a, 07c64e3bce88
Create Date: 2026-03-04 01:15:10.804378+00:00
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic
revision: str = "ac7627fc4b56"
down_revision: Union[str, None] = ("a6920921396a", "07c64e3bce88")
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade database schema."""
    pass


def downgrade() -> None:
    """Downgrade database schema."""
    pass
