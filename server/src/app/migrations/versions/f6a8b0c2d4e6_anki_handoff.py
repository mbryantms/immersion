"""Persistent, source-bound Anki handoff and deferred export choices."""

from alembic import op
import sqlalchemy as sa

revision = "f6a8b0c2d4e6"
down_revision = "e5f7a9b1c3d5"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column(
        "saved_item",
        sa.Column("export_deferred", sa.Boolean, nullable=False, server_default=sa.false()),
    )
    op.create_table(
        "export_attempt",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("job_id", sa.Integer, sa.ForeignKey("job.id"), nullable=False),
        sa.Column("saved_item_id", sa.Integer, sa.ForeignKey("saved_item.id", ondelete="SET NULL")),
        sa.Column("original_saved_item_id", sa.Integer, nullable=False),
        sa.Column("export_key", sa.String, nullable=False),
        sa.Column("snapshot", sa.JSON, nullable=False),
        sa.Column("status", sa.String, nullable=False),
        sa.Column("note_id", sa.Integer),
        sa.Column("error", sa.Text),
        sa.Column("warnings", sa.JSON, nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_export_attempt_saved", "export_attempt", ["saved_item_id", "id"])
    op.create_index("ix_export_attempt_job", "export_attempt", ["job_id"])
    op.create_index("ix_saved_export_inbox", "saved_item", ["archived", "export_deferred", "id"])
    op.create_index("ix_review_graduated_saved", "review_state", ["graduated", "saved_item_id"])
    op.create_index("ix_anki_link_saved", "anki_link", ["saved_item_id"])


def downgrade():
    op.drop_index("ix_anki_link_saved", table_name="anki_link")
    op.drop_index("ix_review_graduated_saved", table_name="review_state")
    op.drop_index("ix_saved_export_inbox", table_name="saved_item")
    op.drop_table("export_attempt")
    op.drop_column("saved_item", "export_deferred")
