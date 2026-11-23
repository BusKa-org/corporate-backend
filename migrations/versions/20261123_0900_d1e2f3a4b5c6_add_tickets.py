"""add tickets (politica, saldo, movimento) and the trip cost columns

Revision ID: d1e2f3a4b5c6
Revises: c0d1e2f3a4b5
Create Date: 2026-11-23 09:00:00.000000+00:00
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "d1e2f3a4b5c6"
down_revision: Union[str, None] = "c0d1e2f3a4b5"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # O tipo sentido_viagem já existe, criado com horario_rota.
    sentido = postgresql.ENUM("IDA", "VOLTA", "CIRCULAR", name="sentido_viagem", create_type=False)

    op.create_table(
        "politica_ticket",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("organizacao_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("grupo_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("usuario_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("nome", sa.String(length=100), nullable=False),
        sa.Column(
            "tipo",
            sa.Enum("RECARGA", "COTA", "ILIMITADO", name="tipo_politica_ticket"),
            nullable=False,
        ),
        sa.Column("vigencia_inicio", sa.Date(), nullable=True),
        sa.Column("vigencia_fim", sa.Date(), nullable=True),
        sa.Column("teto", sa.Integer(), nullable=True),
        sa.Column("recarga_quantidade", sa.Integer(), nullable=True),
        sa.Column("recarga_intervalo_minutos", sa.Integer(), nullable=True),
        sa.Column("recarga_dias_semana", postgresql.ARRAY(sa.Integer()), nullable=True),
        sa.Column(
            "janela",
            sa.Enum("DIA", "SEMANA", "MES", "HORAS", name="janela_cota_ticket"),
            nullable=True,
        ),
        sa.Column("janela_horas", sa.Integer(), nullable=True),
        sa.Column("devolve_ao_finalizar", sa.Boolean(), nullable=False, server_default="false"),
        sa.Column("no_show_penalidade", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("cancelamento_prazo_horas", sa.Integer(), nullable=True),
        sa.Column("antecedencia_min_horas", sa.Integer(), nullable=True),
        sa.Column("antecedencia_max_dias", sa.Integer(), nullable=True),
        sa.Column("rota_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("sentido", sentido, nullable=True),
        sa.Column("horario_de", sa.Time(), nullable=True),
        sa.Column("horario_ate", sa.Time(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.CheckConstraint(
            "grupo_id IS NULL OR usuario_id IS NULL", name="ck_politica_ticket_um_alvo"
        ),
        sa.ForeignKeyConstraint(["organizacao_id"], ["organizacao.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["grupo_id"], ["grupo.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["usuario_id"], ["aluno.usuario_id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["rota_id"], ["rota.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("idx_politica_ticket_organizacao", "politica_ticket", ["organizacao_id"])
    op.create_index("idx_politica_ticket_grupo", "politica_ticket", ["grupo_id"])
    op.create_index("idx_politica_ticket_usuario", "politica_ticket", ["usuario_id"])

    op.create_table(
        "saldo_ticket",
        sa.Column("usuario_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("politica_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("quantidade", sa.Integer(), nullable=False),
        sa.Column("bonus", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("referencia_em", sa.DateTime(timezone=True), nullable=False),
        sa.Column("aguardando_aviso", sa.Boolean(), nullable=False, server_default="false"),
        sa.ForeignKeyConstraint(["usuario_id"], ["aluno.usuario_id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["politica_id"], ["politica_ticket.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("usuario_id", "politica_id"),
    )

    op.create_table(
        "movimento_ticket",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("usuario_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("politica_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("viagem_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column(
            "tipo",
            sa.Enum("GASTO", "DEVOLUCAO", "CONCESSAO", "NO_SHOW", name="tipo_movimento_ticket"),
            nullable=False,
        ),
        sa.Column("quantidade", sa.Integer(), nullable=False),
        sa.Column("motivo", sa.String(length=255), nullable=True),
        sa.Column("criado_por", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(["usuario_id"], ["aluno.usuario_id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["politica_id"], ["politica_ticket.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["viagem_id"], ["viagem.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["criado_por"], ["usuario.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "idx_movimento_ticket_politica", "movimento_ticket", ["politica_id", "created_at"]
    )
    op.create_index(
        "idx_movimento_ticket_usuario", "movimento_ticket", ["usuario_id", "created_at"]
    )

    op.add_column(
        "alunos_confirmados", sa.Column("politica_ticket_id", postgresql.UUID(as_uuid=True))
    )
    op.create_foreign_key(
        "fk_alunos_confirmados_politica_ticket",
        "alunos_confirmados",
        "politica_ticket",
        ["politica_ticket_id"],
        ["id"],
        ondelete="SET NULL",
    )
    op.add_column(
        "alunos_confirmados",
        sa.Column("tickets_gastos", sa.Integer(), nullable=False, server_default="0"),
    )
    op.add_column(
        "viagem", sa.Column("custo_tickets", sa.Integer(), nullable=False, server_default="1")
    )
    op.add_column(
        "horario_rota", sa.Column("custo_tickets", sa.Integer(), nullable=False, server_default="1")
    )


def downgrade() -> None:
    op.drop_column("horario_rota", "custo_tickets")
    op.drop_column("viagem", "custo_tickets")
    op.drop_column("alunos_confirmados", "tickets_gastos")
    op.drop_constraint(
        "fk_alunos_confirmados_politica_ticket", "alunos_confirmados", type_="foreignkey"
    )
    op.drop_column("alunos_confirmados", "politica_ticket_id")

    op.drop_index("idx_movimento_ticket_usuario", table_name="movimento_ticket")
    op.drop_index("idx_movimento_ticket_politica", table_name="movimento_ticket")
    op.drop_table("movimento_ticket")
    op.drop_table("saldo_ticket")
    op.drop_index("idx_politica_ticket_usuario", table_name="politica_ticket")
    op.drop_index("idx_politica_ticket_grupo", table_name="politica_ticket")
    op.drop_index("idx_politica_ticket_organizacao", table_name="politica_ticket")
    op.drop_table("politica_ticket")

    sa.Enum(name="tipo_movimento_ticket").drop(op.get_bind(), checkfirst=True)
    sa.Enum(name="janela_cota_ticket").drop(op.get_bind(), checkfirst=True)
    sa.Enum(name="tipo_politica_ticket").drop(op.get_bind(), checkfirst=True)
