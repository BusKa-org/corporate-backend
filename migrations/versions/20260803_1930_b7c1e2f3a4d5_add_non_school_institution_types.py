"""add non-school institution types

Revision ID: b7c1e2f3a4d5
Revises: f4ea939b97d7
Create Date: 2026-08-03 19:30:00.000000+00:00

RF-02 atende UFCG, UEPB, PaqTcPB e CITTA. As duas últimas não são escolas, e o
enum só tinha tipos do catálogo escolar herdado. Sem estes valores, cadastrar o
PaqTcPB exigiria classificá-lo como universidade — dado errado gravado só para
caber no enum.
"""

from collections.abc import Sequence

from alembic import op

revision: str = "b7c1e2f3a4d5"
down_revision: str | None = "f4ea939b97d7"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


NOVOS_TIPOS = ("PARQUE_TECNOLOGICO", "CENTRO_INOVACAO")
TIPOS_ESCOLARES = (
    "INSTITUTO_FEDERAL",
    "UNIVERSIDADE_PUBLICA",
    "UNIVERSIDADE_PRIVADA",
    "ESCOLA_PUBLICA",
    "ESCOLA_PRIVADA",
    "ESCOLA_COMUNITARIA",
)


def upgrade() -> None:
    for valor in NOVOS_TIPOS:
        op.execute(f"ALTER TYPE tipo_instituicao ADD VALUE IF NOT EXISTS '{valor}'")


def downgrade() -> None:
    # As instituições não-escolares perdem o tipo correto e viram o mais
    # próximo disponível; sem isso o cast abaixo falha.
    removidos = "', '".join(NOVOS_TIPOS)
    op.execute(
        "UPDATE instituicao SET tipo = 'UNIVERSIDADE_PUBLICA' "
        f"WHERE tipo::text IN ('{removidos}')"
    )

    escolares = "', '".join(TIPOS_ESCOLARES)
    op.execute("ALTER TYPE tipo_instituicao RENAME TO tipo_instituicao_old")
    op.execute(f"CREATE TYPE tipo_instituicao AS ENUM ('{escolares}')")
    op.execute(
        "ALTER TABLE instituicao ALTER COLUMN tipo TYPE tipo_instituicao "
        "USING tipo::text::tipo_instituicao"
    )
    op.execute("DROP TYPE tipo_instituicao_old")
