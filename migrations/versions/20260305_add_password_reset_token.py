"""add password_reset_token table

Revision ID: 20260305_reset
Revises: e1d4dadb9200
Create Date: 2026-03-05

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision: str = "20260305_reset"
down_revision: Union[str, None] = "e1d4dadb9200"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "password_reset_token",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column(
            "user_id",
            postgresql.UUID(as_uuid=True),
            nullable=False,
        ),
        sa.Column("token", sa.String(64), nullable=False),
        sa.Column(
            "expires_at",
            sa.DateTime(timezone=True),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(["user_id"], ["usuario.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("token"),
    )
    op.create_index(
        "idx_password_reset_token_expires_at",
        "password_reset_token",
        ["expires_at"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index("idx_password_reset_token_expires_at", "password_reset_token")
    op.drop_table("password_reset_token")
