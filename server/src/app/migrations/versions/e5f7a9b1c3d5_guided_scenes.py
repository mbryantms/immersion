"""Resumable guided scenes and explicitly reviewed local questions."""

from alembic import op
import sqlalchemy as sa

revision = "e5f7a9b1c3d5"
down_revision = "d4e6f8a0b2c4"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column(
        "learning_evidence",
        sa.Column(
            "valid_for_summary", sa.Boolean, nullable=False, server_default=sa.true()
        ),
    )
    op.create_table(
        "guided_scene",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("request_uuid", sa.String, nullable=False, unique=True),
        sa.Column(
            "item_id", sa.Integer, sa.ForeignKey("media_item.id"), nullable=False
        ),
        sa.Column("goal", sa.String, nullable=False),
        sa.Column("snapshot", sa.JSON, nullable=False),
        sa.Column("stage", sa.String, nullable=False),
        sa.Column("revision", sa.Integer, nullable=False),
        sa.Column("support", sa.JSON, nullable=False),
        sa.Column("revisits", sa.Integer, nullable=False),
        sa.Column("due_at", sa.DateTime(timezone=True)),
        sa.Column("completed_at", sa.DateTime(timezone=True)),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_guided_scene_due", "guided_scene", ["due_at"])
    op.create_table(
        "scene_question",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column(
            "scene_id", sa.Integer, sa.ForeignKey("guided_scene.id"), nullable=False
        ),
        sa.Column("revision", sa.Integer, nullable=False),
        sa.Column("status", sa.String, nullable=False),
        sa.Column("body", sa.JSON, nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_scene_question_scene", "scene_question", ["scene_id"])


def downgrade():
    op.drop_column("learning_evidence", "valid_for_summary")
    op.drop_table("scene_question")
    op.drop_table("guided_scene")
