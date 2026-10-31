"""add battery telemetry and boarding time

Revision ID: d2ce717f75b5
Revises: e5f6a7b8c9d0
Create Date: 2026-08-03 16:48:34.410238+00:00

Esta revisão criava também o ciclo da rodada sob demanda (estados OCIOSA/EM_ROTA,
janela por rota, status da solicitação em alunos_confirmados). Esse ciclo foi
substituído pelo da PR #7 (e7f8a9b0c1d2, f8a9b0c1d2e3), e como esta revisão nunca
foi aplicada fora de desenvolvimento, ela foi reescrita para criar só o que
sobrou: a telemetria de bateria (RF-22) e o horário do embarque (RF-17).

Constraints nomeadas explicitamente: o autogenerate emite `None`, que já quebrou
o downgrade deste repositório antes (ver TODO.md, débito 2).
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic
revision: str = "d2ce717f75b5"
down_revision: str | None = "e5f6a7b8c9d0"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Upgrade database schema."""
    op.create_table(
        "telemetria_veiculo",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("veiculo_id", sa.UUID(), nullable=False),
        sa.Column("viagem_id", sa.UUID(), nullable=True),
        sa.Column("timestamp", sa.DateTime(timezone=True), nullable=False),
        sa.Column("nivel_bateria", sa.Numeric(precision=5, scale=2), nullable=True),
        sa.Column("consumo_kwh", sa.Numeric(precision=10, scale=3), nullable=True),
        sa.Column("autonomia_km", sa.Numeric(precision=10, scale=2), nullable=True),
        sa.Column("odometro_km", sa.Numeric(precision=12, scale=2), nullable=True),
        sa.Column("saude_bateria", sa.Numeric(precision=5, scale=2), nullable=True),
        sa.CheckConstraint(
            "nivel_bateria IS NULL OR (nivel_bateria >= 0 AND nivel_bateria <= 100)",
            name="ck_telemetria_nivel_bateria",
        ),
        sa.ForeignKeyConstraint(
            ["veiculo_id"],
            ["onibus.id"],
            name="telemetria_veiculo_veiculo_id_fkey",
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["viagem_id"],
            ["viagem.id"],
            name="telemetria_veiculo_viagem_id_fkey",
            ondelete="SET NULL",
        ),
        sa.PrimaryKeyConstraint("id", name="telemetria_veiculo_pkey"),
    )
    op.create_index("idx_telemetria_veiculo_ts", "telemetria_veiculo", ["veiculo_id", "timestamp"])
    op.create_index("ix_telemetria_veiculo_veiculo_id", "telemetria_veiculo", ["veiculo_id"])

    op.add_column(
        "alunos_confirmados", sa.Column("embarcado_em", sa.DateTime(timezone=True), nullable=True)
    )


def downgrade() -> None:
    """Downgrade database schema."""
    op.drop_column("alunos_confirmados", "embarcado_em")

    op.drop_index("ix_telemetria_veiculo_veiculo_id", table_name="telemetria_veiculo")
    op.drop_index("idx_telemetria_veiculo_ts", table_name="telemetria_veiculo")
    op.drop_table("telemetria_veiculo")
