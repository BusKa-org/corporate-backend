"""guardian consent flow — rename pai/mae to guardian, add minor fields

Revision ID: d4e5f6a7b8c9
Revises: c3d4e5f6a7b8
Create Date: 2026-04-08 10:00:00.000000+00:00
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op


revision: str = 'd4e5f6a7b8c9'
down_revision: Union[str, None] = 'c3d4e5f6a7b8'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Rename pai → responsavel (keep one guardian, not two)
    op.alter_column('aluno', 'nome_pai', new_column_name='nome_responsavel')
    op.alter_column('aluno', 'cpf_pai', new_column_name='cpf_responsavel')

    # Drop the separate mae columns
    op.drop_column('aluno', 'nome_mae')
    op.drop_column('aluno', 'cpf_mae')

    # New minor / guardian consent fields
    op.add_column('aluno', sa.Column('data_nascimento', sa.Date(), nullable=True))
    op.add_column('aluno', sa.Column('email_responsavel', sa.String(120), nullable=True))
    op.add_column('aluno', sa.Column('guardian_token', sa.String(64), nullable=True))
    op.add_column('aluno', sa.Column('guardian_consented_at', sa.DateTime(timezone=True), nullable=True))

    op.create_index('idx_aluno_guardian_token', 'aluno', ['guardian_token'], unique=True)


def downgrade() -> None:
    op.drop_index('idx_aluno_guardian_token', table_name='aluno')
    op.drop_column('aluno', 'guardian_consented_at')
    op.drop_column('aluno', 'guardian_token')
    op.drop_column('aluno', 'email_responsavel')
    op.drop_column('aluno', 'data_nascimento')

    op.add_column('aluno', sa.Column('nome_mae', sa.String(100), nullable=True))
    op.add_column('aluno', sa.Column('cpf_mae', sa.String(14), nullable=True))

    op.alter_column('aluno', 'cpf_responsavel', new_column_name='cpf_pai')
    op.alter_column('aluno', 'nome_responsavel', new_column_name='nome_pai')
