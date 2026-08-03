"""increase sizes in instituicao fields

Revision ID: edd55e85bcdd
Revises: dcc0d379db3c
Create Date: 2026-04-08 03:59:18.277664+00:00
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic
revision: str = 'edd55e85bcdd'
down_revision: Union[str, None] = 'dcc0d379db3c'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

def upgrade():
    op.alter_column(
        "instituicao",
        "sigla",
        existing_type=sa.String(length=30),
        type_=sa.String(length=40),
        existing_nullable=True,
    )

    op.alter_column(
        "instituicao",
        "organizacao_academica",
        existing_type=sa.String(length=50),
        type_=sa.String(length=80),
        existing_nullable=True,
    )

    op.alter_column(
        "instituicao",
        "categoria_administrativa",
        existing_type=sa.String(length=50),
        type_=sa.String(length=80),
        existing_nullable=True,
    )


def downgrade():

    op.alter_column(
        "instituicao",
        "categoria_administrativa",
        existing_type=sa.String(length=80),
        type_=sa.String(length=50),
        existing_nullable=True,
    )

    op.alter_column(
        "instituicao",
        "organizacao_academica",
        existing_type=sa.String(length=150),
        type_=sa.String(length=50),
        existing_nullable=True,
    )

    op.alter_column(
        "instituicao",
        "sigla",
        existing_type=sa.String(length=100),
        type_=sa.String(length=30),
        existing_nullable=True,
    )
