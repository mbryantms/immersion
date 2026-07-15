"""Append-only learner event ingestion. client_uuid makes batch replay
idempotent (the client buffers and flushes with sendBeacon on unload)."""

from __future__ import annotations

from datetime import datetime, timezone

from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlalchemy import text
from sqlalchemy.dialects.sqlite import insert as sqlite_insert
from sqlalchemy.orm import Session

from ..db import get_session
from ..models import Event

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


_BUMP_LOOKUP = text("""
    INSERT INTO lexeme_stats (lexeme_id, encounters, lookups, distinct_items, first_seen, last_seen)
    VALUES (:lex, 0, 1, 0, :now, :now)
    ON CONFLICT(lexeme_id) DO UPDATE SET lookups = lookups + 1, last_seen = :now
""")

_BUMP_ENCOUNTERS = text("""
    INSERT INTO lexeme_stats (lexeme_id, encounters, lookups, distinct_items, first_seen, last_seen)
    SELECT DISTINCT current.lexeme_id, 1, 0,
        CASE WHEN :item IS NOT NULL AND NOT EXISTS (
            SELECT 1
            FROM event previous_event
            JOIN token_occurrence previous_token
              ON previous_token.sentence_id = previous_event.sentence_id
            WHERE previous_event.type = 'sentence_played'
              AND previous_event.item_id = :item
              AND previous_event.client_uuid != :uuid
              AND previous_token.lexeme_id = current.lexeme_id
              AND previous_event.id > COALESCE((
                  SELECT MAX(reset_event.id)
                  FROM event reset_event
                  WHERE reset_event.type = 'lexeme_stats_reset'
                    AND reset_event.lexeme_id = current.lexeme_id
              ), 0)
        ) THEN 1 ELSE 0 END,
        :now, :now
    FROM token_occurrence current
    WHERE current.sentence_id = :sid
    ON CONFLICT(lexeme_id) DO UPDATE SET
        encounters = encounters + 1,
        distinct_items = distinct_items + excluded.distinct_items,
        last_seen = :now
""")


@router.post("/events/batch")
def post_events(events: list[EventIn], session: Session = Depends(get_session)):
    now = datetime.now(timezone.utc)
    inserted = 0
    for ev in events[:500]:
        stmt = (
            sqlite_insert(Event)
            .values(ts=now, **ev.model_dump())
            .on_conflict_do_nothing(index_elements=["client_uuid"])
        )
        if session.execute(stmt).rowcount == 0:
            continue  # replayed event: counters already bumped
        inserted += 1
        if ev.type == "lookup" and ev.lexeme_id:
            session.execute(_BUMP_LOOKUP, {"lex": ev.lexeme_id, "now": now.isoformat()})
            # a lookup contradicts derived familiarity: demote immediately.
            # This self-correction is what makes passive promotion safe.
            from ..models import KnowledgeState

            ks = session.get(KnowledgeState, ev.lexeme_id)
            if ks is not None and ks.source == "derived" and ks.state in ("familiar", "known"):
                ks.state = "learning"
                ks.updated_at = now
        elif ev.type == "sentence_played" and ev.sentence_id:
            session.execute(_BUMP_ENCOUNTERS, {
                "sid": ev.sentence_id,
                "item": ev.item_id,
                "uuid": ev.client_uuid,
                "now": now.isoformat(),
            })
    session.commit()
    return {"inserted": inserted}
