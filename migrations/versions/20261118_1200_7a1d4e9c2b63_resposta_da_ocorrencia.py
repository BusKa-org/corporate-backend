"""ocorrencia: manager's reply (resposta, respondida_em, respondida_por_id)

Revision ID: 7a1d4e9c2b63
Revises: 3f9c2b7e8d41
Create Date: 2026-11-18 12:00:00.000000+00:00
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic
revision: str = "7a1d4e9c2b63"
down_revision: Union[str, None] = "3f9c2b7e8d41"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade database schema."""
    op.add_column("ocorrencia", sa.Column("resposta", sa.Text(), nullable=True))
    op.add_column(
        "ocorrencia", sa.Column("respondida_em", sa.DateTime(timezone=True), nullable=True)
    )
    op.add_column(
        "ocorrencia",
        sa.Column("respondida_por_id", postgresql.UUID(as_uuid=True), nullable=True),
    )
    op.create_foreign_key(
        "fk_ocorrencia_respondida_por_id",
        "ocorrencia",
        "usuario",
        ["respondida_por_id"],
        ["id"],
        ondelete="SET NULL",
    )


def downgrade() -> None:
    """Downgrade database schema."""
    op.drop_constraint("fk_ocorrencia_respondida_por_id", "ocorrencia", type_="foreignkey")
    op.drop_column("ocorrencia", "respondida_por_id")
    op.drop_column("ocorrencia", "respondida_em")
    op.drop_column("ocorrencia", "resposta")
