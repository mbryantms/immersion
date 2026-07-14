"""text_track.meta (embedded stream index) and anki_sentence (already-in-Anki badges)

Revision ID: f1a7c3e9b2d6
Revises: d7e2f5a1c8b4
Create Date: 2026-07-14
"""
from alembic import op
import sqlalchemy as sa


revision = 'f1a7c3e9b2d6'
down_revision = 'd7e2f5a1c8b4'
branch_labels = None
depends_on = None


def upgrade() -> None:
    with op.batch_alter_table('text_track') as batch:
        batch.add_column(sa.Column('meta', sa.JSON(), nullable=True))
    op.create_table(
        'anki_sentence',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('note_id', sa.Integer(), nullable=False),
        sa.Column('deck', sa.String(), nullable=True),
        sa.Column('zh_norm', sa.Text(), nullable=False),
        sa.Column('imported_at', sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('zh_norm'),
    )


def downgrade() -> None:
    op.drop_table('anki_sentence')
    with op.batch_alter_table('text_track') as batch:
        batch.drop_column('meta')
