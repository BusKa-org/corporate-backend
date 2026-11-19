"""projeto: projects of the organization's alunos, aluno.projeto_id

Revision ID: 4e2b7c9d1a56
Revises: 8b1d4e6f2a93
Create Date: 2026-11-18 13:00:00.000000+00:00
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic
revision: str = "4e2b7c9d1a56"
down_revision: Union[str, None] = "8b1d4e6f2a93"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade database schema."""
    op.create_table(
        "projeto",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            server_default=sa.text("uuid_generate_v4()"),
            nullable=False,
        ),
        sa.Column("organizacao_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("nome", sa.String(length=100), nullable=False),
        sa.Column("ativo", sa.Boolean(), server_default=sa.true(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=True,
        ),
        sa.ForeignKeyConstraint(["organizacao_id"], ["organizacao.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_projeto_organizacao_id", "projeto", ["organizacao_id"])
    op.create_index(
        "uq_projeto_organizacao_nome",
        "projeto",
        ["organizacao_id", sa.text("lower(nome)")],
        unique=True,
    )

    op.add_column("aluno", sa.Column("projeto_id", postgresql.UUID(as_uuid=True), nullable=True))
    op.create_foreign_key(
        "aluno_projeto_id_fkey", "aluno", "projeto", ["projeto_id"], ["id"], ondelete="SET NULL"
    )
    op.create_index("ix_aluno_projeto_id", "aluno", ["projeto_id"])


def downgrade() -> None:
    """Downgrade database schema."""
    op.drop_index("ix_aluno_projeto_id", table_name="aluno")
    op.drop_constraint("aluno_projeto_id_fkey", "aluno", type_="foreignkey")
    op.drop_column("aluno", "projeto_id")
    op.drop_index("uq_projeto_organizacao_nome", table_name="projeto")
    op.drop_index("ix_projeto_organizacao_id", table_name="projeto")
    op.drop_table("projeto")
