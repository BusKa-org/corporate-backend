"""add PENDING_APPROVAL to user_status enum

Revision ID: c3d4e5f6a7b8
Revises: 7bb68b5bee12
Create Date: 2026-04-08 09:00:00.000000+00:00
"""
from typing import Sequence, Union

from alembic import op


revision: str = 'c3d4e5f6a7b8'
down_revision: Union[str, None] = '7bb68b5bee12'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute("ALTER TYPE user_status ADD VALUE IF NOT EXISTS 'PENDING_APPROVAL'")


def downgrade() -> None:
    # PostgreSQL does not support removing values from an enum type.
    pass
