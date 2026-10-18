"""Permanent sentence identities and reversible local correction history."""

from alembic import op
import sqlalchemy as sa

revision = "c3d5e7f9a1b2"
down_revision = "a2b4c6d8e0f1"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "sentence_identity",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("item_id", sa.Integer, sa.ForeignKey("media_item.id")),
        sa.Column("track_id", sa.Integer),
        sa.Column("source", sa.JSON, nullable=False),
        sa.Column("revision", sa.Integer, nullable=False),
        sa.Column("overrides", sa.JSON),
        sqlite_autoincrement=True,
    )
    op.create_index("ix_sentence_identity_item_id", "sentence_identity", ["item_id"])
    op.create_table(
        "sentence_correction",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("sentence_id", sa.Integer, sa.ForeignKey("sentence_identity.id"), nullable=False),
        sa.Column("revision", sa.Integer, nullable=False),
        sa.Column("action", sa.String, nullable=False),
        sa.Column("overrides", sa.JSON, nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("sentence_id", "revision"),
    )
    op.create_index("ix_sentence_correction_sentence_id", "sentence_correction", ["sentence_id"])
    # Capture existing source rows without changing their IDs or contents.
    connection = op.get_bind()
    import json

    for row in connection.execute(
        sa.text("SELECT s.*, m.fingerprint FROM sentence s JOIN media_item m ON m.id=s.item_id")
    ).mappings():
        source = {
            key: row[key]
            for key in (
                "zh",
                "en",
                "en_source",
                "t0_ms",
                "t1_ms",
                "ordinal",
                "align_conf",
                "fingerprint",
            )
        }
        source["analysis"] = (
            json.loads(row["analysis"]) if isinstance(row["analysis"], str) else row["analysis"]
        )
        connection.execute(
            sa.text(
                "INSERT INTO sentence_identity(id,item_id,track_id,source,revision) VALUES(:id,:item,:track,:source,0)"
            ),
            {
                "id": row["id"],
                "item": row["item_id"],
                "track": row["track_id"],
                "source": json.dumps(source, ensure_ascii=False),
            },
        )
    # Reserve IDs still present only in the append-only event history.
    maximum = connection.scalar(
        sa.text(
            "SELECT max(value) FROM (SELECT max(id) value FROM sentence UNION ALL SELECT max(sentence_id) FROM event)"
        )
    )
    if maximum:
        connection.execute(
            sa.text(
                "INSERT OR IGNORE INTO sentence_identity(id,source,revision) VALUES(:id,'{}',0)"
            ),
            {"id": maximum},
        )


def downgrade():
    op.drop_table("sentence_correction")
    op.drop_table("sentence_identity")
