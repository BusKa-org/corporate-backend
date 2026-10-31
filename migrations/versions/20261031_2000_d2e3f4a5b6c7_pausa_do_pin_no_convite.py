"""convite: wrong PIN guesses across every PIN, and a timed pause after too many

Each new PIN reset pin_tentativas, so a new PIN per minute gave 5 guesses a
minute for the 7 days of the invitation. pin_erros_total is not reset by a
new PIN. When it reaches the limit, PIN entry pauses until pin_bloqueado_ate;
the pause ending (or the gestor resending the invitation) resets it.

Revision ID: d2e3f4a5b6c7
Revises: c1d2e3f4a5b6
Create Date: 2026-10-31 20:00:00.000000+00:00
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic
revision: str = "d2e3f4a5b6c7"
down_revision: Union[str, None] = "c1d2e3f4a5b6"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade database schema."""
    op.add_column(
        "convite",
        sa.Column("pin_erros_total", sa.Integer(), nullable=False, server_default="0"),
    )
    op.add_column(
        "convite",
        sa.Column("pin_bloqueado_ate", sa.DateTime(timezone=True), nullable=True),
    )


def downgrade() -> None:
    """Downgrade database schema."""
    op.drop_column("convite", "pin_bloqueado_ate")
    op.drop_column("convite", "pin_erros_total")
