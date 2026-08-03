"""initial schema

Revision ID: e1d4dadb9200
Revises:
Create Date: 2026-01-27 12:46:02.444309+00:00
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic
revision: str = "e1d4dadb9200"
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Create initial database schema."""
    # Note: Extensions (postgis, uuid-ossp) are created by database/init-extensions.sql
    # which runs on container startup before Alembic migrations.

    # Create ENUM types
    op.execute(
        "CREATE TYPE dia_da_semana AS ENUM ('SEG', 'TER', 'QUA', 'QUI', 'SEX', 'SAB', 'DOM')"
    )
    op.execute("CREATE TYPE sentido_viagem AS ENUM ('IDA', 'VOLTA', 'CIRCULAR')")
    op.execute(
        "CREATE TYPE status_viagem AS ENUM ('AGENDADA', 'EM_ANDAMENTO', 'FINALIZADA', 'CANCELADA')"
    )
    op.execute("CREATE TYPE user_role AS ENUM ('USER', 'ALUNO', 'MOTORISTA', 'GESTOR')")
    op.execute(
        "CREATE TYPE tipo_instituicao AS ENUM ('INSTITUTO_FEDERAL','UNIVERSIDADE_PUBLICA','UNIVERSIDADE_PRIVADA','ESCOLA_PUBLICA','ESCOLA_PRIVADA','ESCOLA_COMUNITARIA')"
    )

    # Create trigger function for updated_at
    op.execute(
        """
        CREATE OR REPLACE FUNCTION trigger_set_timestamp()
        RETURNS TRIGGER AS $$
        BEGIN
          NEW.updated_at = now() AT TIME ZONE 'UTC';
          RETURN NEW;
        END;
        $$ LANGUAGE plpgsql
    """
    )

    # Create prefeitura table
    op.create_table(
        "prefeitura",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            primary_key=True,
            server_default=sa.text("uuid_generate_v4()"),
        ),
        sa.Column("nome", sa.String(150), nullable=False),
        sa.Column("estado", sa.String(2), nullable=False),
        sa.Column("ativo", sa.Boolean, server_default="true"),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("(now() AT TIME ZONE 'UTC')"),
        ),
    )

    # Create ponto table
    op.create_table(
        "ponto",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            primary_key=True,
            server_default=sa.text("uuid_generate_v4()"),
        ),
        sa.Column(
            "prefeitura_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("prefeitura.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("latitude", sa.Numeric(10, 8), nullable=False),
        sa.Column("longitude", sa.Numeric(11, 8), nullable=False),
        sa.Column("apelido", sa.String(100)),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("(now() AT TIME ZONE 'UTC')"),
        ),
    )
    # Add generated column for geometry
    op.execute(
        "ALTER TABLE ponto ADD COLUMN geom GEOMETRY(POINT, 4326) GENERATED ALWAYS AS (ST_SetSRID(ST_MakePoint(longitude, latitude), 4326)) STORED"
    )
    op.create_index("idx_ponto_geom", "ponto", ["geom"], postgresql_using="gist")

    # Create endereco table
    op.create_table(
        "endereco",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            primary_key=True,
            server_default=sa.text("uuid_generate_v4()"),
        ),
        sa.Column("logradouro", sa.String(150)),
        sa.Column("numero", sa.String(20)),
        sa.Column("bairro", sa.String(100)),
        sa.Column("cidade", sa.String(100)),
        sa.Column("cep", sa.String(10)),
        sa.Column(
            "ponto_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("ponto.id", ondelete="SET NULL"),
        ),
    )

    # Create instituicao table
    op.create_table(
        "instituicao",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            primary_key=True,
            server_default=sa.text("uuid_generate_v4()"),
        ),
        sa.Column("nome", sa.String(150), nullable=False),
        sa.Column("cnpj", sa.String(20)),
        sa.Column(
            "tipo",
            postgresql.ENUM(
                "INSTITUTO_FEDERAL",
                "UNIVERSIDADE_PUBLICA",
                "UNIVERSIDADE_PRIVADA",
                "ESCOLA_PUBLICA",
                "ESCOLA_PRIVADA",
                "ESCOLA_COMUNITARIA",
                name="tipo_instituicao",
                create_type=False,
            ),
            nullable=False,
            server_default="ESCOLA_PUBLICA",
        ),
        sa.Column(
            "ponto_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("ponto.id", ondelete="CASCADE"),
            nullable=False,
        ),
    )

    # Create usuario table
    op.create_table(
        "usuario",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            primary_key=True,
            server_default=sa.text("uuid_generate_v4()"),
        ),
        sa.Column(
            "prefeitura_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("prefeitura.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("nome", sa.String(100), nullable=False),
        sa.Column("email", sa.String(120), unique=True, nullable=False),
        sa.Column("senha_hash", sa.String(255), nullable=False),
        sa.Column("telefone", sa.String(20)),
        sa.Column("cpf", sa.String(14), unique=True, nullable=False),
        sa.Column(
            "role",
            postgresql.ENUM(
                "USER", "ALUNO", "MOTORISTA", "GESTOR", name="user_role", create_type=False
            ),
            nullable=False,
            server_default="ALUNO",
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("(now() AT TIME ZONE 'UTC')"),
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("(now() AT TIME ZONE 'UTC')"),
        ),
    )
    op.create_index("idx_usuario_prefeitura", "usuario", ["prefeitura_id"])

    # Create motorista table
    op.create_table(
        "motorista",
        sa.Column(
            "usuario_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("usuario.id", ondelete="CASCADE"),
            primary_key=True,
        ),
        sa.Column("cnh", sa.String(20), unique=True, nullable=False),
    )

    # Create gestor table
    op.create_table(
        "gestor",
        sa.Column(
            "usuario_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("usuario.id", ondelete="CASCADE"),
            primary_key=True,
        ),
        sa.Column("matricula", sa.String(50)),
        sa.Column("salario", sa.Numeric(10, 2)),
    )

    # Create aluno table
    op.create_table(
        "aluno",
        sa.Column(
            "usuario_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("usuario.id", ondelete="CASCADE"),
            primary_key=True,
        ),
        sa.Column("matricula", sa.String(50)),
        sa.Column("nome_pai", sa.String(100)),
        sa.Column("cpf_pai", sa.String(14)),
        sa.Column("nome_mae", sa.String(100)),
        sa.Column("cpf_mae", sa.String(14)),
        sa.Column("instituicao_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("instituicao.id")),
        sa.Column("ponto_casa_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("ponto.id")),
    )

    # Create onibus table
    op.create_table(
        "onibus",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            primary_key=True,
            server_default=sa.text("uuid_generate_v4()"),
        ),
        sa.Column(
            "prefeitura_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("prefeitura.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("placa", sa.String(10), unique=True, nullable=False),
        sa.Column("modelo", sa.String(50)),
        sa.Column("capacidade", sa.Integer, nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("(now() AT TIME ZONE 'UTC')"),
        ),
    )

    # Create rota table
    op.create_table(
        "rota",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            primary_key=True,
            server_default=sa.text("uuid_generate_v4()"),
        ),
        sa.Column(
            "prefeitura_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("prefeitura.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("nome", sa.String(100), nullable=False),
        sa.Column(
            "motorista_padrao_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("motorista.usuario_id", ondelete="SET NULL"),
        ),
        sa.Column(
            "veiculo_padrao_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("onibus.id", ondelete="SET NULL"),
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("(now() AT TIME ZONE 'UTC')"),
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("(now() AT TIME ZONE 'UTC')"),
        ),
    )

    # Create rota_ponto table
    op.create_table(
        "rota_ponto",
        sa.Column(
            "rota_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("rota.id", ondelete="CASCADE"),
            primary_key=True,
        ),
        sa.Column(
            "ponto_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("ponto.id", ondelete="RESTRICT"),
            primary_key=True,
        ),
        sa.Column("ordem", sa.Integer, nullable=False),
    )

    # Create rota_aluno table
    op.create_table(
        "rota_aluno",
        sa.Column(
            "rota_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("rota.id", ondelete="CASCADE"),
            primary_key=True,
        ),
        sa.Column(
            "aluno_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("aluno.usuario_id", ondelete="CASCADE"),
            primary_key=True,
        ),
        sa.Column("data_inscricao", sa.DateTime, server_default=sa.text("NOW()")),
    )

    # Create horario_rota table
    op.create_table(
        "horario_rota",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            primary_key=True,
            server_default=sa.text("uuid_generate_v4()"),
        ),
        sa.Column(
            "rota_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("rota.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("horario_saida", sa.Time, nullable=False),
        sa.Column(
            "sentido",
            postgresql.ENUM("IDA", "VOLTA", "CIRCULAR", name="sentido_viagem", create_type=False),
            nullable=False,
        ),
    )

    # Create dias_operacao table
    op.create_table(
        "dias_operacao",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            primary_key=True,
            server_default=sa.text("uuid_generate_v4()"),
        ),
        sa.Column(
            "horario_rota_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("horario_rota.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "dia",
            postgresql.ENUM(
                "SEG",
                "TER",
                "QUA",
                "QUI",
                "SEX",
                "SAB",
                "DOM",
                name="dia_da_semana",
                create_type=False,
            ),
            nullable=False,
        ),
    )

    # Create viagem table
    op.create_table(
        "viagem",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            primary_key=True,
            server_default=sa.text("uuid_generate_v4()"),
        ),
        sa.Column("data", sa.Date, nullable=False),
        sa.Column(
            "horario_rota_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("horario_rota.id", ondelete="SET NULL"),
        ),
        sa.Column(
            "motorista_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("motorista.usuario_id", ondelete="RESTRICT"),
        ),
        sa.Column(
            "veiculo_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("onibus.id", ondelete="RESTRICT"),
        ),
        sa.Column(
            "status",
            postgresql.ENUM(
                "AGENDADA",
                "EM_ANDAMENTO",
                "FINALIZADA",
                "CANCELADA",
                name="status_viagem",
                create_type=False,
            ),
            server_default="AGENDADA",
        ),
        sa.Column("inicio_real", sa.DateTime(timezone=True)),
        sa.Column("fim_real", sa.DateTime(timezone=True)),
        sa.Column("km_real", sa.Numeric(10, 2)),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("(now() AT TIME ZONE 'UTC')"),
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("(now() AT TIME ZONE 'UTC')"),
        ),
    )

    # Create viagem_ponto table
    op.create_table(
        "viagem_ponto",
        sa.Column(
            "viagem_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("viagem.id", ondelete="CASCADE"),
            primary_key=True,
        ),
        sa.Column(
            "ponto_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("ponto.id", ondelete="RESTRICT"),
            primary_key=True,
        ),
        sa.Column("ordem", sa.Integer, nullable=False),
        sa.Column("visitado", sa.Boolean, server_default="false"),
        sa.Column("chegada_estimada", sa.DateTime(timezone=True)),
        sa.Column("chegada_real", sa.DateTime(timezone=True)),
    )

    # Create alunos_confirmados table
    op.create_table(
        "alunos_confirmados",
        sa.Column(
            "viagem_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("viagem.id", ondelete="CASCADE"),
            primary_key=True,
        ),
        sa.Column(
            "aluno_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("aluno.usuario_id", ondelete="CASCADE"),
            primary_key=True,
        ),
        sa.Column("confirmacao", sa.Boolean, server_default="true"),
        sa.Column("ponto_embarque_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("ponto.id")),
        sa.Column("ponto_destino_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("ponto.id")),
    )

    # Create notificacoes table
    op.create_table(
        "notificacoes",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            primary_key=True,
            server_default=sa.text("uuid_generate_v4()"),
        ),
        sa.Column(
            "usuario_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("usuario.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("titulo", sa.String(120), nullable=False),
        sa.Column("mensagem", sa.Text, nullable=False),
        sa.Column("enviada", sa.Boolean, server_default="false"),
        sa.Column("data_envio", sa.DateTime(timezone=True)),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("(now() AT TIME ZONE 'UTC')"),
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("(now() AT TIME ZONE 'UTC')"),
        ),
    )
    op.create_index("idx_notificacoes_usuario", "notificacoes", ["usuario_id"])

    # Create triggers for updated_at
    op.execute(
        "CREATE TRIGGER set_timestamp_usuario BEFORE UPDATE ON usuario FOR EACH ROW EXECUTE PROCEDURE trigger_set_timestamp()"
    )
    op.execute(
        "CREATE TRIGGER set_timestamp_rota BEFORE UPDATE ON rota FOR EACH ROW EXECUTE PROCEDURE trigger_set_timestamp()"
    )
    op.execute(
        "CREATE TRIGGER set_timestamp_viagem BEFORE UPDATE ON viagem FOR EACH ROW EXECUTE PROCEDURE trigger_set_timestamp()"
    )


def downgrade() -> None:
    """Drop all tables and types."""
    # Drop triggers
    op.execute("DROP TRIGGER IF EXISTS set_timestamp_viagem ON viagem")
    op.execute("DROP TRIGGER IF EXISTS set_timestamp_rota ON rota")
    op.execute("DROP TRIGGER IF EXISTS set_timestamp_usuario ON usuario")

    # Drop tables in reverse order
    op.drop_table("notificacoes")
    op.drop_table("alunos_confirmados")
    op.drop_table("viagem_ponto")
    op.drop_table("viagem")
    op.drop_table("dias_operacao")
    op.drop_table("horario_rota")
    op.drop_table("rota_aluno")
    op.drop_table("rota_ponto")
    op.drop_table("rota")
    op.drop_table("onibus")
    op.drop_table("aluno")
    op.drop_table("gestor")
    op.drop_table("motorista")
    op.drop_table("usuario")
    op.drop_table("instituicao")
    op.drop_table("endereco")
    op.drop_index("idx_ponto_geom", table_name="ponto")
    op.drop_table("ponto")
    op.drop_table("prefeitura")

    # Drop trigger function
    op.execute("DROP FUNCTION IF EXISTS trigger_set_timestamp()")

    # Drop ENUM types
    op.execute("DROP TYPE IF EXISTS tipo_instituicao")
    op.execute("DROP TYPE IF EXISTS user_role")
    op.execute("DROP TYPE IF EXISTS status_viagem")
    op.execute("DROP TYPE IF EXISTS sentido_viagem")
    op.execute("DROP TYPE IF EXISTS dia_da_semana")

    # Note: Not dropping PostGIS extensions as they may be used by other things
