"""review_state table + sentence_fts (FTS5, pre-segmented CJK columns)

Revision ID: b3c9d1a4e7f2
Revises: 7d45e8539575
Create Date: 2026-07-13
"""
from alembic import op
import sqlalchemy as sa


revision = 'b3c9d1a4e7f2'
down_revision = '7d45e8539575'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        'review_state',
        sa.Column('saved_item_id', sa.Integer(), nullable=False),
        sa.Column('rung', sa.Integer(), nullable=False),
        sa.Column('due_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('passes', sa.Integer(), nullable=False),
        sa.Column('fails', sa.Integer(), nullable=False),
        sa.Column('streak', sa.Integer(), nullable=False),
        sa.Column('graduated', sa.Boolean(), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(['saved_item_id'], ['saved_item.id']),
        sa.PrimaryKeyConstraint('saved_item_id'),
    )
    op.create_index('ix_review_due', 'review_state', ['due_at'])
    # unicode61 doesn't segment CJK: index pre-segmented text instead.
    # rowid = sentence.id; rows are replaced wholesale on re-ingest.
    op.execute(
        "CREATE VIRTUAL TABLE sentence_fts USING fts5("
        "zh_words, zh_chars, trad_words, pinyin, en)"
    )


def downgrade() -> None:
    op.execute("DROP TABLE sentence_fts")
    op.drop_index('ix_review_due', table_name='review_state')
    op.drop_table('review_state')
