"""add REJECTED user status and rejection reason

Revision ID: f4ea939b97d7
Revises: e3df828a86c6
Create Date: 2026-08-03 18:20:00.000000+00:00

RF-02, fluxo secundário 2. Sem um estado próprio, a recusa cairia em DISABLED,
que já significa "conta anonimizada por exclusão" (RF-20) e "desativada pelo
gestor" — três situações distintas indistinguíveis no painel.

O downgrade devolve os recusados para DISABLED, que é o comportamento anterior,
antes de recriar o tipo sem o valor novo.
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "f4ea939b97d7"
down_revision: str | None = "e3df828a86c6"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


USER_STATUS_ANTERIOR = ("PENDING_SIGNUP", "PENDING_APPROVAL", "ACTIVE", "DISABLED")


def upgrade() -> None:
    op.execute("ALTER TYPE user_status ADD VALUE IF NOT EXISTS 'REJECTED'")
    op.add_column("usuario", sa.Column("motivo_rejeicao", sa.Text(), nullable=True))


def downgrade() -> None:
    op.drop_column("usuario", "motivo_rejeicao")

    op.execute("UPDATE usuario SET status = 'DISABLED' WHERE status::text = 'REJECTED'")

    anteriores = "', '".join(USER_STATUS_ANTERIOR)
    op.execute("ALTER TYPE user_status RENAME TO user_status_old")
    op.execute(f"CREATE TYPE user_status AS ENUM ('{anteriores}')")
    # `usuario.status` não tem default no banco — o default é do lado do
    # Python. O DROP abaixo é no-op hoje e existe só para o cast não quebrar
    # caso um server_default apareça depois; nada é reposto, senão o downgrade
    # inventaria um default que nunca existiu.
    op.execute("ALTER TABLE usuario ALTER COLUMN status DROP DEFAULT")
    op.execute(
        "ALTER TABLE usuario ALTER COLUMN status TYPE user_status "
        "USING status::text::user_status"
    )
    op.execute("DROP TYPE user_status_old")
