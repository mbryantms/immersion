"""Additive Mandarin occurrence and saved-sense metadata. Legacy IDs stay intact."""
from alembic import op
import sqlalchemy as sa

revision = "a2b4c6d8e0f1"
down_revision = "e8c1b6f4a9d3"
branch_labels = None
depends_on = None


def upgrade():
    for name, kind in (("start_offset", sa.Integer), ("end_offset", sa.Integer),
                       ("canonical", sa.String), ("reading", sa.String)):
        op.add_column("token_occurrence", sa.Column(name, kind(), nullable=True))
    for name, kind in (("selected_reading", sa.String), ("selected_meaning", sa.Text),
                       ("selection_source", sa.String)):
        op.add_column("saved_item", sa.Column(name, kind(), nullable=True))


def downgrade():
    for name in ("selection_source", "selected_meaning", "selected_reading"):
        op.drop_column("saved_item", name)
    for name in ("reading", "canonical", "end_offset", "start_offset"):
        op.drop_column("token_occurrence", name)
