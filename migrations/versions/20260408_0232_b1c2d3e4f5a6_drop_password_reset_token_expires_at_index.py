"""drop_password_reset_token_expires_at_index

Revision ID: b1c2d3e4f5a6
Revises: a1b2c3d4e5f6
Create Date: 2026-04-08 02:32:00.000000+00:00
"""

from typing import Sequence, Union

from alembic import op


# revision identifiers, used by Alembic
revision: str = "b1c2d3e4f5a6"
down_revision: Union[str, None] = "a1b2c3d4e5f6"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade database schema."""
    op.drop_index("idx_password_reset_token_expires_at", table_name="password_reset_token")


def downgrade() -> None:
    """Downgrade database schema."""
    op.create_index(
        "idx_password_reset_token_expires_at",
        "password_reset_token",
        ["expires_at"],
        unique=False,
    )
