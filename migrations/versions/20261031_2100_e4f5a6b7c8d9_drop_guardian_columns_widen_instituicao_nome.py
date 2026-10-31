"""drop aluno.guardian_token

The guardian consent endpoints were removed, so nothing issues this token
anymore. The model still declared it with a unique constraint while the
migration had created a unique index, which made `alembic check` fail.

Revision ID: e4f5a6b7c8d9
Revises: c1d2e3f4a5b6
Create Date: 2026-10-31 21:00:00.000000+00:00
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic
revision: str = "e4f5a6b7c8d9"
down_revision: Union[str, None] = "c1d2e3f4a5b6"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade database schema."""
    op.drop_index("idx_aluno_guardian_token", table_name="aluno")
    op.drop_column("aluno", "guardian_token")


def downgrade() -> None:
    """Downgrade database schema."""
    op.add_column("aluno", sa.Column("guardian_token", sa.String(64), nullable=True))
    op.create_index("idx_aluno_guardian_token", "aluno", ["guardian_token"], unique=True)
