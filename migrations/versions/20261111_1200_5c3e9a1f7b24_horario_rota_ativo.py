"""horario_rota.ativo: retire schedules that already have trips instead of deleting them

Trips read horario_saida and sentido live from horario_rota, so editing or
deleting a schedule rewrote or wiped past trips. Also fills viagem.rota_id for
legacy fixed trips that only point at their schedule.

Revision ID: 5c3e9a1f7b24
Revises: d2e3f4a5b6c7
Create Date: 2026-11-11 12:00:00.000000+00:00
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic
revision: str = "5c3e9a1f7b24"
down_revision: Union[str, None] = "d2e3f4a5b6c7"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade database schema."""
    op.add_column(
        "horario_rota",
        sa.Column("ativo", sa.Boolean(), nullable=False, server_default=sa.true()),
    )
    op.execute(
        "UPDATE viagem SET rota_id = horario_rota.rota_id FROM horario_rota "
        "WHERE viagem.horario_rota_id = horario_rota.id AND viagem.rota_id IS NULL"
    )


def downgrade() -> None:
    """Downgrade database schema. The rota_id backfill is kept: it is correct data."""
    op.drop_column("horario_rota", "ativo")
