"""add DRT lifecycle, availability windows, consent and battery telemetry

Revision ID: d2ce717f75b5
Revises: a1b2c3d4e5f7
Create Date: 2026-08-03 16:48:34.410238+00:00

Escrita a partir do autogenerate, com quatro correções que ele não faz sozinho:

1. Valores novos de `status_viagem` — o autogenerate não compara enums. PG 16
   aceita ALTER TYPE ... ADD VALUE dentro da transação desde que o valor novo
   não seja usado nela; só adicionamos aqui, o uso vem depois.
2. `dia_da_semana` já existe: referenciada com `create_type=False`, senão o
   CREATE TABLE tenta recriar o tipo e falha.
3. Constraints nomeadas explicitamente. O autogenerate emite `None`, que já
   quebrou o downgrade deste repositório antes (ver TODO.md, débito 2).
4. O downgrade derruba os tipos que criou. Tipo órfão faz o próximo upgrade
   falhar com "type ... already exists" — mesmo defeito, mesma origem.

O churn do índice `idx_aluno_guardian_token` que o autogenerate detectou é
drift pré-existente, alheio a esta mudança, e foi removido daqui.
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic
revision: str = "d2ce717f75b5"
down_revision: str | None = "a1b2c3d4e5f7"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


NOVOS_STATUS_VIAGEM = ("OCIOSA", "SOLICITADA", "BUFFER_ABERTO", "EM_ROTA")
STATUS_VIAGEM_LEGADO = ("AGENDADA", "EM_ANDAMENTO", "FINALIZADA", "CANCELADA")

# Já existe no banco desde o schema inicial — só referenciada, nunca recriada.
dia_da_semana = postgresql.ENUM(
    "SEG", "TER", "QUA", "QUI", "SEX", "SAB", "DOM", name="dia_da_semana", create_type=False
)

status_solicitacao = postgresql.ENUM(
    "INTERESSADO", "CONFIRMADO", "NEGADO", "CANCELADO", name="status_solicitacao"
)


def upgrade() -> None:
    """Upgrade database schema."""
    for valor in NOVOS_STATUS_VIAGEM:
        op.execute(f"ALTER TYPE status_viagem ADD VALUE IF NOT EXISTS '{valor}'")

    status_solicitacao.create(op.get_bind(), checkfirst=True)

    op.create_table(
        "consentimento",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("usuario_id", sa.UUID(), nullable=False),
        sa.Column("versao_termo", sa.String(length=20), nullable=False),
        sa.Column(
            "aceito_em",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column("revogado_em", sa.DateTime(timezone=True), nullable=True),
        sa.Column("ip_origem", sa.String(length=45), nullable=True),
        sa.ForeignKeyConstraint(
            ["usuario_id"], ["usuario.id"], name="consentimento_usuario_id_fkey", ondelete="CASCADE"
        ),
        sa.PrimaryKeyConstraint("id", name="consentimento_pkey"),
    )
    op.create_index(
        "idx_consentimento_usuario_versao", "consentimento", ["usuario_id", "versao_termo"]
    )
    op.create_index("ix_consentimento_usuario_id", "consentimento", ["usuario_id"])

    op.create_table(
        "janela_disponibilidade",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("organizacao_id", sa.UUID(), nullable=False),
        sa.Column("rota_id", sa.UUID(), nullable=False),
        sa.Column("motorista_id", sa.UUID(), nullable=False),
        sa.Column("veiculo_id", sa.UUID(), nullable=True),
        sa.Column("dia", dia_da_semana, nullable=False),
        sa.Column("hora_inicio", sa.Time(), nullable=False),
        sa.Column("hora_fim", sa.Time(), nullable=False),
        sa.Column("buffer_minutos", sa.Integer(), server_default="5", nullable=False),
        sa.Column("ativo", sa.Boolean(), server_default="true", nullable=False),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=True
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=True
        ),
        sa.CheckConstraint("buffer_minutos > 0", name="ck_janela_buffer_positivo"),
        sa.CheckConstraint("hora_fim > hora_inicio", name="ck_janela_ordem_horas"),
        sa.ForeignKeyConstraint(
            ["motorista_id"],
            ["motorista.usuario_id"],
            name="janela_disponibilidade_motorista_id_fkey",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["organizacao_id"],
            ["organizacao.id"],
            name="janela_disponibilidade_organizacao_id_fkey",
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["rota_id"], ["rota.id"], name="janela_disponibilidade_rota_id_fkey", ondelete="CASCADE"
        ),
        sa.ForeignKeyConstraint(
            ["veiculo_id"],
            ["onibus.id"],
            name="janela_disponibilidade_veiculo_id_fkey",
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id", name="janela_disponibilidade_pkey"),
    )
    op.create_index("idx_janela_org_dia", "janela_disponibilidade", ["organizacao_id", "dia"])

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
        "alunos_confirmados",
        sa.Column(
            "status",
            status_solicitacao,
            server_default="INTERESSADO",
            nullable=False,
        ),
    )
    op.add_column(
        "alunos_confirmados",
        sa.Column(
            "solicitado_em",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=True,
        ),
    )
    op.add_column(
        "alunos_confirmados", sa.Column("declarado_em", sa.DateTime(timezone=True), nullable=True)
    )
    op.add_column("alunos_confirmados", sa.Column("qr_token", sa.String(length=64), nullable=True))
    op.add_column(
        "alunos_confirmados", sa.Column("embarcado_em", sa.DateTime(timezone=True), nullable=True)
    )
    op.create_index(
        "ix_alunos_confirmados_qr_token", "alunos_confirmados", ["qr_token"], unique=True
    )

    # Linhas herdadas: quem já tinha confirmação vira CONFIRMADO, o resto fica
    # INTERESSADO pelo server_default.
    op.execute(
        "UPDATE alunos_confirmados SET status = 'CONFIRMADO' WHERE confirmacao IS TRUE"
    )

    op.add_column("viagem", sa.Column("rota_id", sa.UUID(), nullable=True))
    op.add_column("viagem", sa.Column("janela_id", sa.UUID(), nullable=True))
    op.add_column("viagem", sa.Column("buffer_expira_em", sa.DateTime(timezone=True), nullable=True))
    op.create_foreign_key(
        "viagem_janela_id_fkey",
        "viagem",
        "janela_disponibilidade",
        ["janela_id"],
        ["id"],
        ondelete="SET NULL",
    )
    op.create_foreign_key(
        "viagem_rota_id_fkey", "viagem", "rota", ["rota_id"], ["id"], ondelete="CASCADE"
    )


def downgrade() -> None:
    """Downgrade database schema."""
    op.drop_constraint("viagem_rota_id_fkey", "viagem", type_="foreignkey")
    op.drop_constraint("viagem_janela_id_fkey", "viagem", type_="foreignkey")
    op.drop_column("viagem", "buffer_expira_em")
    op.drop_column("viagem", "janela_id")
    op.drop_column("viagem", "rota_id")

    op.drop_index("ix_alunos_confirmados_qr_token", table_name="alunos_confirmados")
    op.drop_column("alunos_confirmados", "embarcado_em")
    op.drop_column("alunos_confirmados", "qr_token")
    op.drop_column("alunos_confirmados", "declarado_em")
    op.drop_column("alunos_confirmados", "solicitado_em")
    op.drop_column("alunos_confirmados", "status")

    op.drop_index("ix_telemetria_veiculo_veiculo_id", table_name="telemetria_veiculo")
    op.drop_index("idx_telemetria_veiculo_ts", table_name="telemetria_veiculo")
    op.drop_table("telemetria_veiculo")

    op.drop_index("idx_janela_org_dia", table_name="janela_disponibilidade")
    op.drop_table("janela_disponibilidade")

    op.drop_index("ix_consentimento_usuario_id", table_name="consentimento")
    op.drop_index("idx_consentimento_usuario_versao", table_name="consentimento")
    op.drop_table("consentimento")

    status_solicitacao.drop(op.get_bind(), checkfirst=True)

    # Postgres não remove valor de enum: o tipo é recriado sem os novos. As
    # viagens que estiverem num estado da rodada caem no equivalente legado
    # mais próximo, senão o cast falha.
    op.execute(
        "UPDATE viagem SET status = 'EM_ANDAMENTO' WHERE status::text = 'EM_ROTA'"
    )
    op.execute(
        "UPDATE viagem SET status = 'AGENDADA' "
        "WHERE status::text IN ('OCIOSA', 'SOLICITADA', 'BUFFER_ABERTO')"
    )
    legado = "', '".join(STATUS_VIAGEM_LEGADO)
    op.execute("ALTER TYPE status_viagem RENAME TO status_viagem_old")
    op.execute(f"CREATE TYPE status_viagem AS ENUM ('{legado}')")
    # O default da coluna ainda aponta para o tipo antigo e não é convertido
    # sozinho; solta antes do cast e repõe depois.
    op.execute("ALTER TABLE viagem ALTER COLUMN status DROP DEFAULT")
    op.execute(
        "ALTER TABLE viagem ALTER COLUMN status TYPE status_viagem "
        "USING status::text::status_viagem"
    )
    op.execute("ALTER TABLE viagem ALTER COLUMN status SET DEFAULT 'AGENDADA'::status_viagem")
    op.execute("DROP TYPE status_viagem_old")
