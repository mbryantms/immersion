"""lexeme.pos + freq_rank (jieba lexicon) and example_sentence (Tatoeba)

Revision ID: d7e2f5a1c8b4
Revises: b3c9d1a4e7f2
Create Date: 2026-07-14
"""
from alembic import op
import sqlalchemy as sa


revision = 'd7e2f5a1c8b4'
down_revision = 'b3c9d1a4e7f2'
branch_labels = None
depends_on = None


def upgrade() -> None:
    with op.batch_alter_table('lexeme') as batch:
        batch.add_column(sa.Column('pos', sa.String(), nullable=True))
        batch.add_column(sa.Column('freq_rank', sa.Integer(), nullable=True))
    op.create_table(
        'example_sentence',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('zh', sa.Text(), nullable=False),
        sa.Column('zh_simp', sa.Text(), nullable=False),
        sa.Column('en', sa.Text(), nullable=False),
        sa.Column('source', sa.String(), nullable=False),
        sa.PrimaryKeyConstraint('id'),
    )


def downgrade() -> None:
    op.drop_table('example_sentence')
    with op.batch_alter_table('lexeme') as batch:
        batch.drop_column('freq_rank')
        batch.drop_column('pos')
