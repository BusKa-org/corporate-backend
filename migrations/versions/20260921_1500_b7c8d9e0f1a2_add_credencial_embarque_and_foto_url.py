"""add credencial_embarque and foto_url — RF-15

Revision ID: b7c8d9e0f1a2
Revises: a1b2c3d4e5f7
Create Date: 2026-09-21 15:00:00.000000+00:00
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic
revision: str = "b7c8d9e0f1a2"
down_revision: Union[str, None] = "a1b2c3d4e5f7"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("aluno", sa.Column("foto_url", sa.String(255), nullable=True))

    op.create_table(
        "credencial_embarque",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            primary_key=True,
            server_default=sa.text("uuid_generate_v4()"),
        ),
        sa.Column(
            "viagem_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("viagem.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "aluno_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("aluno.usuario_id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "ponto_embarque_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("ponto.id"),
            nullable=False,
        ),
        sa.Column("token", sa.String(64), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("usado", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.UniqueConstraint(
            "viagem_id",
            "aluno_id",
            "ponto_embarque_id",
            name="uq_credencial_embarque_viagem_aluno_ponto",
        ),
        sa.UniqueConstraint("token", name="uq_credencial_embarque_token"),
    )


def downgrade() -> None:
    op.drop_table("credencial_embarque")
    op.drop_column("aluno", "foto_url")
