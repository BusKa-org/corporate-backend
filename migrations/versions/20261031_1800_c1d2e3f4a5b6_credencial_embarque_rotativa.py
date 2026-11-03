"""boarding credential: rotating QR secret, rejection and revocation

The static token gives way to a per-credential secret the student app turns
into a code that changes every step (RF-15). A rejected credential no longer
boards anyone (RF-17), and a re-issued one revokes the previous, so at most one
credential per student and trip is active.

Revision ID: c1d2e3f4a5b6
Revises: f8a9b0c1d2e3
Create Date: 2026-10-31 18:00:00.000000+00:00
"""

import secrets
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic
revision: str = "c1d2e3f4a5b6"
down_revision: Union[str, None] = "f8a9b0c1d2e3"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade database schema."""
    op.add_column("credencial_embarque", sa.Column("segredo", sa.String(64), nullable=True))
    op.add_column(
        "credencial_embarque",
        sa.Column("recusada_em", sa.DateTime(timezone=True), nullable=True),
    )
    op.add_column("credencial_embarque", sa.Column("motivo_recusa", sa.String(32), nullable=True))
    op.add_column(
        "credencial_embarque",
        sa.Column("revogada_em", sa.DateTime(timezone=True), nullable=True),
    )

    conn = op.get_bind()
    ids = conn.execute(sa.text("SELECT id FROM credencial_embarque")).scalars().all()
    for credencial_id in ids:
        conn.execute(
            sa.text("UPDATE credencial_embarque SET segredo = :segredo WHERE id = :id"),
            {"segredo": secrets.token_hex(32), "id": credencial_id},
        )
    op.alter_column("credencial_embarque", "segredo", nullable=False)

    op.drop_constraint("uq_credencial_embarque_token", "credencial_embarque", type_="unique")
    op.drop_column("credencial_embarque", "token")
    op.drop_constraint(
        "uq_credencial_embarque_viagem_aluno_ponto", "credencial_embarque", type_="unique"
    )
    op.create_index(
        "uq_credencial_embarque_ativa",
        "credencial_embarque",
        ["viagem_id", "aluno_id"],
        unique=True,
        postgresql_where=sa.text("revogada_em IS NULL"),
    )


def downgrade() -> None:
    """Downgrade database schema."""
    op.drop_index("uq_credencial_embarque_ativa", table_name="credencial_embarque")
    # As revogadas não cabem na unicidade antiga.
    op.execute("DELETE FROM credencial_embarque WHERE revogada_em IS NOT NULL")
    op.create_unique_constraint(
        "uq_credencial_embarque_viagem_aluno_ponto",
        "credencial_embarque",
        ["viagem_id", "aluno_id", "ponto_embarque_id"],
    )

    op.add_column("credencial_embarque", sa.Column("token", sa.String(64), nullable=True))
    op.execute("UPDATE credencial_embarque SET token = segredo")
    op.alter_column("credencial_embarque", "token", nullable=False)
    op.create_unique_constraint("uq_credencial_embarque_token", "credencial_embarque", ["token"])

    op.drop_column("credencial_embarque", "revogada_em")
    op.drop_column("credencial_embarque", "motivo_recusa")
    op.drop_column("credencial_embarque", "recusada_em")
    op.drop_column("credencial_embarque", "segredo")
