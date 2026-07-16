"""series_name: per-series proper-name lexicon (NER)

Revision ID: e8c1b6f4a9d3
Revises: f1a7c3e9b2d6
Create Date: 2026-07-15
"""
from alembic import op
import sqlalchemy as sa


revision = 'e8c1b6f4a9d3'
down_revision = 'f1a7c3e9b2d6'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        'series_name',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('series_id', sa.Integer(), nullable=False),
        sa.Column('simplified', sa.String(), nullable=False),
        sa.Column('label', sa.String(), nullable=False),
        sa.Column('count', sa.Integer(), nullable=False),
        sa.ForeignKeyConstraint(['series_id'], ['series.id']),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('series_id', 'simplified'),
    )
    op.create_index('ix_series_name_series', 'series_name', ['series_id'])


def downgrade() -> None:
    op.drop_index('ix_series_name_series', table_name='series_name')
    op.drop_table('series_name')
