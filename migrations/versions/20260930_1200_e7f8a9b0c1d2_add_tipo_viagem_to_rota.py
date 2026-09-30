"""add tipo_viagem and on-demand parameters to rota

Revision ID: e7f8a9b0c1d2
Revises: a1b2c3d4e5f7
Create Date: 2026-09-30 12:00:00.000000+00:00
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic
revision: str = "e7f8a9b0c1d2"
down_revision: Union[str, None] = "a1b2c3d4e5f7"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade database schema."""
    postgresql.ENUM("FIXA", "SOB_DEMANDA", name="tipo_viagem").create(
        op.get_bind(), checkfirst=True
    )

    op.add_column(
        "rota",
        sa.Column("tipo", sa.Enum(name="tipo_viagem"), nullable=False, server_default="FIXA"),
    )
    op.add_column("rota", sa.Column("buffer_minutos", sa.Integer(), nullable=True))
    op.add_column("rota", sa.Column("prazo_inicio_minutos", sa.Integer(), nullable=True))
    op.create_check_constraint(
        "ck_rota_parametros_sob_demanda",
        "rota",
        "tipo = 'FIXA' OR (buffer_minutos IS NOT NULL AND prazo_inicio_minutos IS NOT NULL)",
    )


def downgrade() -> None:
    """Downgrade database schema."""
    op.drop_constraint("ck_rota_parametros_sob_demanda", "rota", type_="check")
    op.drop_column("rota", "prazo_inicio_minutos")
    op.drop_column("rota", "buffer_minutos")
    op.drop_column("rota", "tipo")
    postgresql.ENUM(name="tipo_viagem").drop(op.get_bind(), checkfirst=True)
