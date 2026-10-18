"""Append-only learner event ingestion. client_uuid makes batch replay
idempotent (the client buffers and flushes with sendBeacon on unload)."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlalchemy import func, select, text
from sqlalchemy.dialects.sqlite import insert as sqlite_insert
from sqlalchemy.orm import Session

from ..db import get_session
from ..models import (
    Event,
    LearningEvidence,
    LexemeExposure,
    LexemeStats,
    MediaItem,
    Sentence,
    SentenceIdentity,
    TokenOccurrence,
)

router = APIRouter()


class EventIn(BaseModel):
    client_uuid: str
    type: str
    session_id: str | None = None
    item_id: int | None = None
    sentence_id: int | None = None
    lexeme_id: int | None = None
    position_ms: int | None = None
    subtitle_mode: str | None = None
    study_mode: str | None = None
    data: dict | None = None
    occurred_at: datetime | None = None


_BUMP_LOOKUP = text("""
    INSERT INTO lexeme_stats (lexeme_id, encounters, lookups, distinct_items, first_seen, last_seen)
    VALUES (:lex, 0, 1, 0, :now, :now)
    ON CONFLICT(lexeme_id) DO UPDATE SET lookups = lookups + 1, last_seen = max(last_seen, :now)
""")


def _exposure(session: Session, event: Event) -> None:
    sentence = session.get(Sentence, event.sentence_id)
    if sentence is None or sentence.item_id != event.item_id:
        return
    identity = session.get(SentenceIdentity, sentence.id)
    revision = identity.revision if identity else 0
    data = dict(event.data or {})
    if data.get("source_revision", revision) != revision:
        # Offline delivery may refer to an older source. Keep its snapshot,
        # never attribute its words to the current corrected sentence.
        event.data = {**data, "exposure_status": "source_changed"}
        return
    if data.get("timestamp_status") == "future_clock":
        event.data = {**data, "exposure_status": "uncertain_time"}
        return
    lexemes = list(
        session.scalars(
            select(TokenOccurrence.lexeme_id)
            .where(TokenOccurrence.sentence_id == sentence.id)
            .distinct()
        )
    )
    # A delayed pre-reset outbox event remains activity, but cannot refill
    # counters the learner has deliberately cleared.
    resets = dict(
        session.execute(
            select(Event.lexeme_id, func.max(Event.ts))
            .where(Event.type == "lexeme_stats_reset", Event.lexeme_id.in_(lexemes))
            .group_by(Event.lexeme_id)
        ).all()
    )
    lexemes = [
        lid
        for lid in lexemes
        if lid not in resets
        or event.ts.replace(tzinfo=None) > resets[lid].replace(tzinfo=None)
    ]
    event.data = {
        **data,
        "lexeme_ids": lexemes,
        "source_revision": revision,
        "duration_ms": sentence.t1_ms - sentence.t0_ms,
        "exposure_policy": "source-day-v1",
        "item_kind": session.get(MediaItem, sentence.item_id).kind,
    }
    task = event.study_mode or ("listen" if event.subtitle_mode == "off" else "read")
    if not lexemes:
        return
    added = session.scalars(
        sqlite_insert(LexemeExposure)
        .values(
            [
                {
                    "lexeme_id": lid,
                    "item_id": sentence.item_id,
                    "day": event.ts.date().isoformat(),
                    "ts": event.ts,
                    "event_id": event.id,
                    "task": task,
                }
                for lid in lexemes
            ]
        )
        .on_conflict_do_nothing()
        .returning(LexemeExposure.lexeme_id)
    ).all()
    for lid in added:
        items = session.scalar(
            select(func.count(func.distinct(LexemeExposure.item_id))).where(
                LexemeExposure.lexeme_id == lid
            )
        )
        stmt = sqlite_insert(LexemeStats).values(
            lexeme_id=lid,
            encounters=1,
            lookups=0,
            distinct_items=items,
            first_seen=event.ts,
            last_seen=event.ts,
        )
        session.execute(
            stmt.on_conflict_do_update(
                index_elements=["lexeme_id"],
                set_={
                    "encounters": LexemeStats.encounters + 1,
                    "distinct_items": func.max(LexemeStats.distinct_items, items),
                    "first_seen": func.min(LexemeStats.first_seen, event.ts),
                    "last_seen": func.max(LexemeStats.last_seen, event.ts),
                },
            )
        )


@router.post("/events/batch")
def post_events(events: list[EventIn], session: Session = Depends(get_session)):
    now = datetime.now(timezone.utc)
    inserted = 0
    for ev in events[:500]:
        timestamp = ev.occurred_at or now
        if timestamp.tzinfo is None:
            timestamp = timestamp.replace(tzinfo=timezone.utc)
        timestamp = timestamp.astimezone(timezone.utc)
        values = ev.model_dump(exclude={"occurred_at"})
        if timestamp > now + timedelta(minutes=5):
            # Preserve and acknowledge a skewed-device event rather than
            # permanently blocking the durable outbox. Exclude it from evidence.
            values["data"] = {
                **(values.get("data") or {}),
                "reported_occurred_at": timestamp.isoformat(),
                "timestamp_status": "future_clock",
            }
            timestamp = now
        event_id = session.scalar(
            sqlite_insert(Event)
            .values(ts=timestamp, **values)
            .on_conflict_do_nothing(index_elements=["client_uuid"])
            .returning(Event.id)
        )
        if event_id is None:
            continue
        event = session.get(Event, event_id)
        inserted += 1
        if ev.type == "lookup" and ev.lexeme_id:
            session.execute(
                _BUMP_LOOKUP, {"lex": ev.lexeme_id, "now": timestamp.isoformat()}
            )
        elif ev.type == "sentence_played" and ev.sentence_id:
            _exposure(session, event)
        elif (
            ev.type == "review_outcome"
            and ev.study_mode == "dictation"
            and not (event.data or {}).get("timestamp_status")
        ):
            data = ev.data or {}
            score = data.get("score")
            if (
                isinstance(score, (float, int))
                and not isinstance(score, bool)
                and 0 <= score <= 100
            ):
                session.add(
                    LearningEvidence(
                        event_id=event.id,
                        ts=timestamp,
                        task="transcription",
                        method="automatic_edit_distance",
                        assistance=data.get("assistance")
                        if data.get("assistance")
                        in ("none_reported", "text_revealed", "unknown")
                        else "unknown",
                        score=score / 100,
                        scope={
                            "sentence_id": ev.sentence_id,
                            "item_id": ev.item_id,
                            "source_revision": data.get("source_revision"),
                            "expected_zh": data.get("expected_zh"),
                            "script_policy": data.get("script_policy"),
                            "limitation": "Transcription only; does not assess meaning or pronunciation",
                        },
                    )
                )
    session.commit()
    return {"inserted": inserted}
