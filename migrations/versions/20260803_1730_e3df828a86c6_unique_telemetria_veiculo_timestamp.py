"""unique (veiculo_id, timestamp) on telemetria_veiculo

Revision ID: e3df828a86c6
Revises: d2ce717f75b5
Create Date: 2026-08-03 17:30:00.000000+00:00

A ingestão já descarta amostras repetidas por consulta, mas duas requisições
idênticas concorrentes passariam pelas duas verificações antes de qualquer uma
gravar. A chave natural da amostra fecha isso no banco, que é o único lugar
onde a garantia vale sob concorrência.
"""

from collections.abc import Sequence

from alembic import op

revision: str = "e3df828a86c6"
down_revision: str | None = "d2ce717f75b5"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_unique_constraint(
        "uq_telemetria_veiculo_timestamp", "telemetria_veiculo", ["veiculo_id", "timestamp"]
    )


def downgrade() -> None:
    op.drop_constraint("uq_telemetria_veiculo_timestamp", "telemetria_veiculo", type_="unique")
