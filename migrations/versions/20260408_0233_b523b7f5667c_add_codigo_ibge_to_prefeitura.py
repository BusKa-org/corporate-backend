"""add_codigo_ibge_to_prefeitura

Revision ID: b523b7f5667c
Revises: b1c2d3e4f5a6
Create Date: 2026-04-08 02:30:07.263707+00:00
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic
revision: str = "b523b7f5667c"
down_revision: Union[str, None] = "b1c2d3e4f5a6"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade database schema."""
    op.add_column("prefeitura", sa.Column("codigo_ibge", sa.String(length=10), nullable=False))
    op.create_index("ix_prefeitura_codigo_ibge", "prefeitura", ["codigo_ibge"], unique=True)


def downgrade() -> None:
    """Downgrade database schema."""
    op.drop_index("ix_prefeitura_codigo_ibge", table_name="prefeitura")
    op.drop_column("prefeitura", "codigo_ibge")
