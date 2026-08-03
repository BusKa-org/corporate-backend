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
    # Backfill sigla from nome using a GLOBAL row number (not partitioned by
    # base prefix). A per-partition ROW_NUMBER restarts at 1 in every
    # partition, so two different names that truncate to the same 16-char
    # prefix both land as rn=1/2/... in different partitions with identical
    # suffixes -- a collision. Numbering globally guarantees every suffix is
    # unique regardless of prefix collisions, and reserving space for the
    # suffix length (instead of a fixed LEFT(..., 16)) keeps the result
    # within varchar(20) even once rn reaches 4+ digits. `nome` is NOT NULL
    # in the initial schema, so there is no NULL-name case to handle.
    op.execute(
        """
        WITH ranked AS (SELECT id, ROW_NUMBER() OVER (ORDER BY id) AS rn FROM organizacao)
        UPDATE organizacao o
        SET sigla = LEFT(UPPER(REPLACE(o.nome, ' ', '')), 20 - LENGTH('_' || r.rn::text))
                    || '_' || r.rn::text
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

    # Index names survive rename_table/alter_column verbatim, which would
    # otherwise poison the next autogenerate with spurious drop/recreate
    # diffs against the models' organizacao-named indexes. Catalog-only
    # renames, no rebuild.
    op.execute("ALTER INDEX idx_usuario_prefeitura RENAME TO idx_usuario_organizacao")
    op.execute("ALTER INDEX ix_instituicao_prefeitura_id RENAME TO ix_instituicao_organizacao_id")

    # The model declares ativo nullable=False; no prior migration enforced it,
    # so the DB still allows NULL. Backfill before tightening the constraint.
    op.execute("UPDATE organizacao SET ativo = true WHERE ativo IS NULL")
    op.alter_column("organizacao", "ativo", nullable=False)


def downgrade() -> None:
    """Downgrade database schema."""
    op.alter_column("organizacao", "ativo", nullable=True)

    op.execute("ALTER INDEX ix_instituicao_organizacao_id RENAME TO ix_instituicao_prefeitura_id")
    op.execute("ALTER INDEX idx_usuario_organizacao RENAME TO idx_usuario_prefeitura")

    for table in _FK_TABLES:
        op.alter_column(table, "organizacao_id", new_column_name="prefeitura_id")

    # estado was made nullable in upgrade() specifically so corporate tenants
    # can omit a Brazilian state code. Backfill a synthetic value before
    # restoring NOT NULL or any such row aborts the downgrade.
    op.execute("UPDATE organizacao SET estado = 'XX' WHERE estado IS NULL")
    op.alter_column("organizacao", "estado", nullable=False)

    op.add_column("organizacao", sa.Column("codigo_ibge", sa.String(length=10), nullable=True))
    # Do not derive codigo_ibge from sigla via truncation: two siglas can
    # share the same first 10 characters (e.g. sigla values that only differ
    # after the truncation point), which breaks the unique index below. A
    # real IBGE code is meaningless for a corporate tenant anyway, so use a
    # synthetic, collision-free value instead.
    op.execute(
        """
        WITH r AS (SELECT id, ROW_NUMBER() OVER (ORDER BY id) n FROM organizacao)
        UPDATE organizacao o SET codigo_ibge = LPAD(r.n::text, 10, '0') FROM r WHERE r.id = o.id
        """
    )
    op.alter_column("organizacao", "codigo_ibge", nullable=False)
    op.create_index("ix_prefeitura_codigo_ibge", "organizacao", ["codigo_ibge"], unique=True)

    op.drop_index("ix_organizacao_sigla", table_name="organizacao")
    op.drop_column("organizacao", "sigla")

    op.rename_table("organizacao", "prefeitura")
