"""add user status and signup_completed_at

Revision ID: a6920921396a
Revises: e1d4dadb9200
Create Date: 2026-02-17 21:50:51.888337+00:00
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic
revision: str = "a6920921396a"
down_revision: Union[str, None] = "e1d4dadb9200"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade database schema."""
    user_status_enum = postgresql.ENUM(
        "PENDING_SIGNUP",
        "ACTIVE",
        "DISABLED",
        name="user_status",
    )
    user_status_enum.create(op.get_bind(), checkfirst=True)

    # 2) Add column with TEMP default to avoid NOT NULL crash
    op.add_column(
        "usuario",
        sa.Column(
            "status",
            sa.Enum(name="user_status"),
            nullable=False,
            server_default="ACTIVE",
        ),
    )

    # 3) Add signup_completed_at
    op.add_column(
        "usuario",
        sa.Column("signup_completed_at", sa.DateTime(timezone=True), nullable=True),
    )

    # 4) Remove default (clean schema)
    op.alter_column("usuario", "status", server_default=None)


def downgrade() -> None:
    """Downgrade database schema."""
    op.drop_column("usuario", "signup_completed_at")
    op.drop_column("usuario", "status")

    user_status_enum = postgresql.ENUM(
        "PENDING_SIGNUP",
        "ACTIVE",
        "DISABLED",
        name="user_status",
    )
    user_status_enum.drop(op.get_bind(), checkfirst=True)
