"""parametros_operacao: on-demand operation parameters per organization

Revision ID: 3f9c2a7e5b14
Revises: d2e3f4a5b6c7
Create Date: 2026-11-11 12:00:00.000000+00:00
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic
revision: str = "3f9c2a7e5b14"
down_revision: Union[str, None] = "d2e3f4a5b6c7"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade database schema."""
    op.create_table(
        "parametros_operacao",
        sa.Column("organizacao_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("minimo_alunos", sa.Integer(), nullable=False),
        sa.Column("pausa_entre_viagens_minutos", sa.Integer(), nullable=False),
        sa.Column("antecedencia_motorista_minutos", sa.Integer(), nullable=False),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=True,
        ),
        sa.ForeignKeyConstraint(["organizacao_id"], ["organizacao.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("organizacao_id"),
    )


def downgrade() -> None:
    """Downgrade database schema."""
    op.drop_table("parametros_operacao")
