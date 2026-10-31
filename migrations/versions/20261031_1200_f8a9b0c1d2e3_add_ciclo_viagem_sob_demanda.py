"""on-demand trip lifecycle: availability windows, ride requests, trip states

The request also carries the declared route (RF-13) and NEGADA, a request refused
by the segment capacity check (RF-14), counted per stop in the dashboard (RF-21).

Revision ID: f8a9b0c1d2e3
Revises: e7f8a9b0c1d2
Create Date: 2026-10-31 12:00:00.000000+00:00
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic
revision: str = "f8a9b0c1d2e3"
down_revision: Union[str, None] = "e7f8a9b0c1d2"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade database schema."""
    # PG 12+ accepts ADD VALUE inside a transaction as long as the new value
    # is not used in that same transaction, which this migration does not do.
    op.execute("ALTER TYPE status_viagem ADD VALUE IF NOT EXISTS 'SOLICITADA'")
    op.execute("ALTER TYPE status_viagem ADD VALUE IF NOT EXISTS 'BUFFER_ABERTO'")

    op.add_column("viagem", sa.Column("rota_id", postgresql.UUID(as_uuid=True), nullable=True))
    op.create_foreign_key(
        "viagem_rota_id_fkey", "viagem", "rota", ["rota_id"], ["id"], ondelete="SET NULL"
    )
    op.create_index("ix_viagem_rota_id", "viagem", ["rota_id"])
    op.execute(
        "UPDATE viagem SET rota_id = horario_rota.rota_id "
        "FROM horario_rota WHERE viagem.horario_rota_id = horario_rota.id"
    )
    op.add_column("viagem", sa.Column("buffer_fim", sa.DateTime(timezone=True), nullable=True))
    op.add_column(
        "viagem",
        sa.Column("aviso_prazo_enviado", sa.Boolean(), nullable=False, server_default="false"),
    )

    dia_da_semana = postgresql.ENUM(name="dia_da_semana", create_type=False)
    op.create_table(
        "janela_disponibilidade",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "onibus_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("onibus.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "motorista_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("motorista.usuario_id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("dia", dia_da_semana, nullable=False),
        sa.Column("hora_inicio", sa.Time(), nullable=False),
        sa.Column("hora_fim", sa.Time(), nullable=False),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=True
        ),
        sa.CheckConstraint("hora_fim > hora_inicio", name="ck_janela_horario"),
    )
    op.create_index("idx_janela_onibus_dia", "janela_disponibilidade", ["onibus_id", "dia"])
    op.create_index(
        "ix_janela_disponibilidade_motorista_id", "janela_disponibilidade", ["motorista_id"]
    )

    status_solicitacao = postgresql.ENUM(
        "ATIVA",
        "CANCELADA",
        "DESISTENCIA",
        "NEGADA",
        name="status_solicitacao",
        create_type=False,
    )
    status_solicitacao.create(op.get_bind())
    op.create_table(
        "solicitacao_viagem",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
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
        sa.Column("status", status_solicitacao, nullable=False, server_default="ATIVA"),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=True
        ),
        sa.Column("cancelada_em", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "ponto_embarque_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("ponto.id", name="solicitacao_viagem_ponto_embarque_id_fkey"),
            nullable=True,
        ),
        sa.Column(
            "ponto_destino_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("ponto.id", name="solicitacao_viagem_ponto_destino_id_fkey"),
            nullable=True,
        ),
        sa.Column("declarada_em", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index("ix_solicitacao_viagem_aluno_id", "solicitacao_viagem", ["aluno_id"])
    op.create_index(
        "uq_solicitacao_ativa",
        "solicitacao_viagem",
        ["viagem_id", "aluno_id"],
        unique=True,
        postgresql_where=sa.text("status = 'ATIVA'"),
    )


def downgrade() -> None:
    """Downgrade database schema.

    The SOLICITADA/BUFFER_ABERTO values stay in status_viagem: Postgres cannot drop
    enum values. Rows still using them would break the previous code, so they are
    cancelled here.
    """
    op.drop_index("uq_solicitacao_ativa", table_name="solicitacao_viagem")
    op.drop_index("ix_solicitacao_viagem_aluno_id", table_name="solicitacao_viagem")
    op.drop_table("solicitacao_viagem")
    postgresql.ENUM(name="status_solicitacao").drop(op.get_bind())

    op.drop_index("ix_janela_disponibilidade_motorista_id", table_name="janela_disponibilidade")
    op.drop_index("idx_janela_onibus_dia", table_name="janela_disponibilidade")
    op.drop_table("janela_disponibilidade")

    op.execute(
        "UPDATE viagem SET status = 'CANCELADA' "
        "WHERE status::text IN ('SOLICITADA', 'BUFFER_ABERTO')"
    )
    op.drop_column("viagem", "aviso_prazo_enviado")
    op.drop_column("viagem", "buffer_fim")
    op.drop_index("ix_viagem_rota_id", table_name="viagem")
    op.drop_constraint("viagem_rota_id_fkey", "viagem", type_="foreignkey")
    op.drop_column("viagem", "rota_id")
