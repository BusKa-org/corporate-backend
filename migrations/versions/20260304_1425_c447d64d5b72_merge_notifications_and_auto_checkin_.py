"""merge notifications and auto-checkin heads

Revision ID: c447d64d5b72
Revises: 7f4d9fd81526, ac7627fc4b56
Create Date: 2026-03-04 14:25:31.204263+00:00
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic
revision: str = "c447d64d5b72"
down_revision: Union[str, None] = ("7f4d9fd81526", "ac7627fc4b56")
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade database schema."""
    pass


def downgrade() -> None:
    """Downgrade database schema."""
    pass
