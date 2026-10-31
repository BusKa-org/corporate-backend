"""add horario de trabalho and status to motorista

Revision ID: a7b8c9d0e1f2
Revises: e5f6a7b8c9d0
Create Date: 2026-10-21 12:00:00.000000+00:00
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "a7b8c9d0e1f2"
down_revision: Union[str, None] = "e5f6a7b8c9d0"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("motorista", sa.Column("horario_inicio", sa.Time(), nullable=True))
    op.add_column("motorista", sa.Column("horario_fim", sa.Time(), nullable=True))
    op.add_column(
        "motorista",
        sa.Column("dias_trabalho", postgresql.ARRAY(sa.String(length=3)), nullable=True),
    )

    status_motorista = postgresql.ENUM(
        "ATIVO", "EM_ROTA", "EM_DESCANSO", name="status_motorista", create_type=False
    )
    status_motorista.create(op.get_bind(), checkfirst=True)
    op.add_column(
        "motorista",
        sa.Column("status_motorista", status_motorista, nullable=False, server_default="ATIVO"),
    )
    op.add_column("motorista", sa.Column("descanso_ate", sa.DateTime(timezone=True), nullable=True))
    # Motorista com viagem já em andamento entra como EM_ROTA
    op.execute("""
        UPDATE motorista SET status_motorista = 'EM_ROTA'
        WHERE usuario_id IN (SELECT motorista_id FROM viagem WHERE status = 'EM_ANDAMENTO')
        """)


def downgrade() -> None:
    op.drop_column("motorista", "descanso_ate")
    op.drop_column("motorista", "status_motorista")
    postgresql.ENUM(name="status_motorista").drop(op.get_bind(), checkfirst=True)
    op.drop_column("motorista", "dias_trabalho")
    op.drop_column("motorista", "horario_fim")
    op.drop_column("motorista", "horario_inicio")
