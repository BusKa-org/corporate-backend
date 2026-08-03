"""merge_autochecking_notification_reset_heads

Revision ID: fba2f1a067db
Revises: 808effcb7bee, c447d64d5b72
Create Date: 2026-03-10 02:19:02.028508+00:00
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic
revision: str = "fba2f1a067db"
down_revision: Union[str, None] = ("808effcb7bee", "c447d64d5b72")
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade database schema."""
    pass


def downgrade() -> None:
    """Downgrade database schema."""
    pass
