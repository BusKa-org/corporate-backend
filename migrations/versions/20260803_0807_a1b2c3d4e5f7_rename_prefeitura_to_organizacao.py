"""rename_prefeitura_to_organizacao

Revision ID: a1b2c3d4e5f7
Revises: d4e5f6a7b8c9
Create Date: 2026-08-03 08:07:00.000000+00:00
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic
revision: str = "a1b2c3d4e5f7"
down_revision: Union[str, None] = "d4e5f6a7b8c9"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

_FK_TABLES = ("usuario", "onibus", "ponto", "rota", "instituicao")


def upgrade() -> None:
    """Upgrade database schema."""
    op.rename_table("prefeitura", "organizacao")

    op.add_column("organizacao", sa.Column("sigla", sa.String(length=20), nullable=True))
    # Backfill sigla from nome. Ties are broken with a numeric suffix so the
    # backfill can never violate the unique index below, even though the
    # current dev DB has zero rows (verified empty before writing this).
    op.execute(
        """
        WITH ranked AS (
            SELECT id,
                   UPPER(LEFT(REPLACE(nome, ' ', ''), 20)) AS base,
                   ROW_NUMBER() OVER (
                       PARTITION BY UPPER(LEFT(REPLACE(nome, ' ', ''), 20))
                       ORDER BY id
                   ) AS rn
            FROM organizacao
        )
        UPDATE organizacao o
        SET sigla = CASE WHEN r.rn = 1 THEN r.base ELSE LEFT(r.base, 16) || '_' || r.rn::text END
        FROM ranked r
        WHERE r.id = o.id
        """
    )
    op.alter_column("organizacao", "sigla", nullable=False)
    op.create_index("ix_organizacao_sigla", "organizacao", ["sigla"], unique=True)

    op.drop_index("ix_prefeitura_codigo_ibge", table_name="organizacao")
    op.drop_column("organizacao", "codigo_ibge")
    op.alter_column("organizacao", "estado", nullable=True)

    for table in _FK_TABLES:
        op.alter_column(table, "prefeitura_id", new_column_name="organizacao_id")


def downgrade() -> None:
    """Downgrade database schema."""
    for table in _FK_TABLES:
        op.alter_column(table, "organizacao_id", new_column_name="prefeitura_id")

    op.alter_column("organizacao", "estado", nullable=False)
    op.add_column("organizacao", sa.Column("codigo_ibge", sa.String(length=10), nullable=True))
    op.execute("UPDATE organizacao SET codigo_ibge = LEFT(REPLACE(sigla, '_', ''), 10)")
    op.alter_column("organizacao", "codigo_ibge", nullable=False)
    op.create_index("ix_prefeitura_codigo_ibge", "organizacao", ["codigo_ibge"], unique=True)

    op.drop_index("ix_organizacao_sigla", table_name="organizacao")
    op.drop_column("organizacao", "sigla")

    op.rename_table("organizacao", "prefeitura")
