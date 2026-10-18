"""Task-specific learner evidence and bounded passive exposure."""

from alembic import op
import sqlalchemy as sa

revision = "d4e6f8a0b2c4"
down_revision = "c3d5e7f9a1b2"
branch_labels = None
depends_on = None


def upgrade():
    op.create_index("ix_event_type_study_ts", "event", ["type", "study_mode", "ts"])
    op.create_table(
        "lexeme_exposure",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("lexeme_id", sa.Integer, sa.ForeignKey("lexeme.id"), nullable=False),
        sa.Column(
            "item_id", sa.Integer, sa.ForeignKey("media_item.id"), nullable=False
        ),
        sa.Column("day", sa.String, nullable=False),
        sa.Column("ts", sa.DateTime(timezone=True), nullable=False),
        sa.Column("task", sa.String, nullable=False),
        sa.Column("event_id", sa.Integer, nullable=False),
        sa.UniqueConstraint("lexeme_id", "item_id", "day"),
    )
    op.create_index("ix_exposure_lexeme", "lexeme_exposure", ["lexeme_id"])
    op.create_table(
        "learning_evidence",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("event_id", sa.Integer, nullable=False, unique=True),
        sa.Column("lexeme_id", sa.Integer, sa.ForeignKey("lexeme.id")),
        sa.Column("ts", sa.DateTime(timezone=True), nullable=False),
        sa.Column("task", sa.String, nullable=False),
        sa.Column("method", sa.String, nullable=False),
        sa.Column("assistance", sa.String, nullable=False),
        sa.Column("score", sa.Float, nullable=False),
        sa.Column("scope", sa.JSON, nullable=False),
    )
    op.create_index("ix_evidence_lexeme_ts", "learning_evidence", ["lexeme_id", "ts"])
    # Preserve the original inference in the append-only trail. Neither legacy
    # passive counts nor self-graded reviews establish whole-word mastery.
    op.execute("""INSERT INTO event(type,ts,lexeme_id,data)
        SELECT 'knowledge_policy_migrated', CURRENT_TIMESTAMP, lexeme_id,
        json_object('previous_state',state,'previous_source',source,
                    'state','familiar','policy','evidence-v1')
        FROM knowledge_state WHERE source='derived' AND state='known'""")
    op.execute(
        "UPDATE knowledge_state SET state='familiar' WHERE source='derived' AND state='known'"
    )


def downgrade():
    op.drop_table("learning_evidence")
    op.drop_table("lexeme_exposure")
    op.drop_index("ix_event_type_study_ts", table_name="event")
    # Do not recreate unsupported mastery claims or erase migration audit events.
