"""Behavioral checks for scoped evidence, offline exposure and explainable ranking."""

# ruff: noqa: F811 — pytest fixtures intentionally shadow their imports
from datetime import datetime, timedelta, timezone
from pathlib import Path

from sqlalchemy import select

from app.models import (
    Event,
    KnowledgeState,
    LearningEvidence,
    LexemeExposure,
    MediaItem,
    Sentence,
    SentenceIdentity,
    TextTrack,
    TokenOccurrence,
)
from test_api import client, db_session, seeded  # noqa: F401


def play(seeded, uuid, when=None, **data):
    return {
        "client_uuid": uuid,
        "type": "sentence_played",
        "item_id": seeded["item"],
        "sentence_id": seeded["sentence"],
        "study_mode": "listen",
        "subtitle_mode": "off",
        **({"occurred_at": when.isoformat()} if when else {}),
        "data": data,
    }


def test_repeated_loops_and_retries_are_activity_not_independent_evidence(
    client, seeded
):
    batch = [play(seeded, str(i)) for i in range(40)]
    assert client.post("/api/events/batch", json=batch).json()["inserted"] == 40
    assert client.post("/api/events/batch", json=batch).json()["inserted"] == 0
    info = client.get(f"/api/lexemes/{seeded['lexeme']}").json()
    assert info["stats"]["encounters"] == 1
    assert info["evidence"]["exposure"]["independent_encounters"] == 1
    dashboard = client.get("/api/stats/dashboard").json()
    assert dashboard["totals"]["sentences_played"] == 40


def test_offline_events_keep_original_days_and_out_of_order_delivery(
    client, seeded, db_session
):
    now = datetime.now(timezone.utc)
    batch = [play(seeded, "today", now), play(seeded, "old", now - timedelta(days=3))]
    assert client.post("/api/events/batch", json=batch).status_code == 200
    with db_session() as session:
        assert session.query(LexemeExposure).count() == 2
        events = session.scalars(select(Event).order_by(Event.id)).all()
        assert events[1].ts < events[0].ts
    assert (
        client.get(f"/api/lexemes/{seeded['lexeme']}").json()["evidence"]["exposure"][
            "days"
        ]
        == 2
    )


def test_future_clock_preserves_event_without_blocking_outbox_or_creating_evidence(
    client, seeded, db_session
):
    future = datetime.now(timezone.utc) + timedelta(days=1)
    response = client.post(
        "/api/events/batch",
        json=[play(seeded, "valid"), play(seeded, "future", future)],
    )
    assert response.json()["inserted"] == 2
    with db_session() as session:
        assert session.query(Event).count() == 2
        assert session.query(LexemeExposure).count() == 1
        event = session.scalar(select(Event).where(Event.client_uuid == "future"))
        assert event.data["timestamp_status"] == "future_clock"
        assert event.data["exposure_status"] == "uncertain_time"


def test_exposure_uses_utc_day_and_does_not_refill_reset_from_delayed_old_events(
    client, seeded, db_session
):
    now = datetime.now(timezone.utc) - timedelta(days=2)
    same = now.astimezone(timezone(timedelta(hours=14)))
    client.post(
        "/api/events/batch",
        json=[play(seeded, "utc", now), play(seeded, "other-offset", same)],
    )
    with db_session() as session:
        assert session.query(LexemeExposure).one().day == now.date().isoformat()
    client.delete(f"/api/lexemes/{seeded['lexeme']}/stats")
    client.post("/api/events/batch", json=[play(seeded, "delayed-before-reset", now)])
    with db_session() as session:
        assert session.query(LexemeExposure).count() == 0


def test_source_revision_change_does_not_reassign_old_exposure(
    client, seeded, db_session
):
    with db_session() as session:
        session.add(
            SentenceIdentity(
                id=seeded["sentence"], item_id=seeded["item"], source={}, revision=2
            )
        )
        session.commit()
    client.post(
        "/api/events/batch", json=[play(seeded, "old-source", source_revision=1)]
    )
    with db_session() as session:
        assert session.query(LexemeExposure).count() == 0
        assert session.query(Event).one().data["exposure_status"] == "source_changed"


def test_indexed_and_encountered_populations_and_invalid_filter(client, seeded):
    assert client.get("/api/stats/dashboard?population=library").json()[
        "recurring_unknowns"
    ]
    assert (
        client.get("/api/stats/dashboard?population=encountered").json()[
            "recurring_unknowns"
        ]
        == []
    )
    client.post("/api/events/batch", json=[play(seeded, "heard")])
    assert client.get("/api/stats/dashboard?population=encountered").json()[
        "recurring_unknowns"
    ]
    assert client.get("/api/stats/dashboard?population=invalid").status_code == 422


def test_dictation_is_sentence_transcription_not_word_mastery(
    client, seeded, db_session
):
    event = {
        "client_uuid": "dictation-one",
        "type": "review_outcome",
        "study_mode": "dictation",
        "sentence_id": seeded["sentence"],
        "item_id": seeded["item"],
        "data": {
            "score": 100,
            "expected_zh": "你好。",
            "source_revision": 0,
            "script_policy": "source",
        },
    }
    client.post("/api/events/batch", json=[event, event])
    with db_session() as session:
        evidence = session.query(LearningEvidence).one()
        assert evidence.task == "transcription" and evidence.lexeme_id is None
        assert evidence.assistance == "unknown"
        assert evidence.scope["expected_zh"] == "你好。"
        assert session.get(KnowledgeState, seeded["lexeme"]) is None
    stats = client.get("/api/stats/dashboard").json()["practice_evidence"]
    assert stats == [
        {
            "task": "transcription",
            "method": "automatic_edit_distance",
            "assistance": "unknown",
            "attempts": 1,
            "mean_score": 1,
        }
    ]


def test_review_retains_reading_meaning_context_and_retry_identity(
    client, seeded, db_session
):
    saved = client.post(
        "/api/saved-items",
        json={
            "kind": "word",
            "lexeme_id": seeded["lexeme"],
            "sentence_id": seeded["sentence"],
            "surface": "你好",
            "selected_reading": "ni3 hao3",
            "selected_meaning": "hello",
        },
    ).json()
    body = {
        "result": "pass",
        "request_uuid": "same",
        "task": "reading_recall",
        "assistance": "hinted",
        "sentence_id": seeded["sentence"],
        "source_revision": 2,
        "context_zh": "你好。",
    }
    first = client.post(f"/api/review/{saved['id']}/outcome", json=body)
    second = client.post(f"/api/review/{saved['id']}/outcome", json=body)
    assert first.json() == second.json()
    with db_session() as session:
        evidence = session.query(LearningEvidence).one()
        assert evidence.task == "reading_recall" and evidence.assistance == "hinted"
        assert (
            evidence.scope["reading"] == "ni3 hao3"
            and evidence.scope["meaning"] == "hello"
        )
        assert (
            evidence.scope["context_zh"] == "你好。"
            and evidence.scope["source_revision"] == 2
        )
        assert not evidence.scope["delayed"]


def test_exposure_reset_removes_familiarity_and_preserves_retrieval(
    client, seeded, db_session
):
    client.post("/api/events/batch", json=[play(seeded, "reset-me")])
    with db_session() as session:
        session.add(
            KnowledgeState(
                lexeme_id=seeded["lexeme"], state="familiar", source="derived"
            )
        )
        session.add(
            LearningEvidence(
                event_id=100,
                lexeme_id=seeded["lexeme"],
                ts=datetime.now(timezone.utc),
                task="meaning_recall",
                method="self_report",
                assistance="unknown",
                score=1,
                scope={},
            )
        )
        session.commit()
    assert client.delete(f"/api/lexemes/{seeded['lexeme']}/stats").status_code == 200
    info = client.get(f"/api/lexemes/{seeded['lexeme']}").json()
    assert info["state"] == "new"
    assert info["evidence"]["exposure"]["independent_encounters"] == 0
    assert len(info["evidence"]["recent_retrieval"]) == 1


def test_profile_is_optional_and_does_not_mark_beginner_words_known(
    client, seeded, db_session
):
    assert client.get("/api/learner-profile").json()["level"] == "unknown"
    assert (
        client.put(
            "/api/learner-profile",
            json={"level": "beginner", "goal": "read", "interests": [" travel "]},
        ).status_code
        == 200
    )
    assert client.get("/api/learner-profile").json()["interests"] == ["travel"]
    with db_session() as session:
        assert session.query(KnowledgeState).count() == 0
    assert (
        client.put("/api/learner-profile", json={"goal": "impossible"}).status_code
        == 422
    )


def test_recommendation_signals_exclude_ignored_words_and_show_uncertainty(
    client, seeded, db_session
):
    with db_session() as session:
        item = session.get(MediaItem, seeded["item"])
        item.duration_ms = 60000
        session.commit()
    rec = client.get("/api/recommendations").json()["items"][0]
    assert rec["unknowns_per_minute"] == 1
    assert rec["dense_unknowns_30s"] == 1
    assert "unmeasured" in rec["uncertainty"]
    client.put(f"/api/knowledge/{seeded['lexeme']}", json={"state": "ignored"})
    rec = client.get("/api/recommendations").json()["items"][0]
    assert rec["unknowns_per_minute"] == 0
    assert rec["ignored_tokens"] == 1 and rec["eligible_tokens"] == 0


def test_ratings_are_skill_specific_and_change_local_ranking(
    client, seeded, db_session
):
    with db_session() as session:
        original = session.get(MediaItem, seeded["item"])
        original.duration_ms = 60000
        other = MediaItem(
            root_id=original.root_id,
            relpath="b.mp4",
            title="b",
            kind="video",
            ready=True,
            duration_ms=60000,
        )
        session.add(other)
        session.flush()
        track = TextTrack(item_id=other.id, lang="zh", source="sidecar", selected=True)
        session.add(track)
        session.flush()
        sentence = Sentence(
            item_id=other.id,
            track_id=track.id,
            ordinal=0,
            zh="你好",
            t0_ms=0,
            t1_ms=1000,
        )
        session.add(sentence)
        session.flush()
        session.add(
            TokenOccurrence(
                sentence_id=sentence.id,
                idx=0,
                item_id=other.id,
                surface="你好",
                lexeme_id=seeded["lexeme"],
            )
        )
        other_id = other.id
        session.commit()
    client.put("/api/learner-profile", json={"goal": "listen"})
    assert (
        client.post(
            f"/api/items/{seeded['item']}/difficulty",
            json={"goal": "listen", "rating": "too_hard", "position_ms": 60000},
        ).status_code
        == 200
    )
    recs = client.get("/api/recommendations").json()["items"]
    assert recs[0]["item_id"] == other_id
    assert recs[1]["difficulty_rating"] == "too_hard"
    client.put("/api/learner-profile", json={"goal": "read"})
    assert all(
        rec["difficulty_rating"] is None
        for rec in client.get("/api/recommendations").json()["items"]
    )
    assert (
        client.post(
            f"/api/items/{seeded['item']}/difficulty",
            json={"goal": "listen", "rating": "nonsense"},
        ).status_code
        == 422
    )


def test_migration_preserves_original_events_manual_and_anki_evidence(
    tmp_path, monkeypatch
):
    from alembic import command
    from alembic.config import Config
    from sqlalchemy.orm import Session
    from app import db
    from app.config import settings
    from app.models import Lexeme

    monkeypatch.setattr(settings, "data_dir", tmp_path)
    cfg = Config(str(Path(__file__).parents[1] / "src/alembic.ini"))
    cfg.set_main_option(
        "script_location", str(Path(__file__).parents[1] / "src/app/migrations")
    )
    command.upgrade(cfg, "c3d5e7f9a1b2")
    engine = db.make_engine()
    with Session(engine) as session:
        for i, source in enumerate(("derived", "manual", "anki"), 1):
            session.add(Lexeme(id=i, simplified=f"词{i}", is_dict=True))
        session.flush()
        for i, source in enumerate(("derived", "manual", "anki"), 1):
            session.add(
                KnowledgeState(
                    lexeme_id=i,
                    state="known",
                    source=source,
                    anki_interval_days=30 if source == "anki" else None,
                )
            )
        session.add(
            Event(
                type="knowledge_derived",
                lexeme_id=1,
                data={"state": "known", "encounters": 999},
            )
        )
        session.commit()
    db.upgrade_db()
    with Session(engine) as session:
        assert session.get(KnowledgeState, 1).state == "familiar"
        assert session.get(KnowledgeState, 2).state == "known"
        assert session.get(KnowledgeState, 3).anki_interval_days == 30
        assert (
            session.query(Event).filter_by(type="knowledge_derived").one().data["state"]
            == "known"
        )
        assert (
            session.query(Event).filter_by(type="knowledge_policy_migrated").count()
            == 1
        )
        assert session.query(LearningEvidence).count() == 0
    assert list((tmp_path / "backups").glob("*.db"))
