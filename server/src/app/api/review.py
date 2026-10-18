"""Contextual review queue: triage funnel, not an SRS (Anki owns retention).

Fixed 1d -> 3d -> 7d ladder; fail drops a rung. Word reviews prefer a fresh
concordance sentence over the saved context (variability); sentence reviews
are listen-and-reveal, self-graded — no typed input anywhere in review (the
player's dictation panel owns writing practice). Initial practice followed by
three successful delayed reviews surfaces the item for the Anki export
tray."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import func, select, update
from sqlalchemy.dialects.sqlite import insert as sqlite_insert
from sqlalchemy.orm import Session

from ..db import get_session
from ..models import (
    AnkiLink,
    Event,
    MediaItem,
    ReviewState,
    SavedItem,
    Sentence,
    TokenOccurrence,
    Lexeme,
    Sense,
    SentenceIdentity,
)
from ..timing import effective_times

router = APIRouter()

LADDER_DAYS = [1, 3, 7]
SESSION_CAP = 20


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _fresh_context(session: Session, item: SavedItem) -> Sentence | None:
    """A concordance sentence that is NOT one of the saved contexts — later
    reviews should retrieve meaning in a new setting, not recognize the card."""
    if not item.lexeme_id or item.selected_reading or item.selected_meaning:
        return None
    saved_sentence_ids = {c.sentence_id for c in item.contexts if c.sentence_id}
    rows = session.execute(
        select(TokenOccurrence.sentence_id)
        .where(TokenOccurrence.lexeme_id == item.lexeme_id)
        .where(TokenOccurrence.sentence_id.not_in(saved_sentence_ids or {0}))
        .order_by(func.random())
        .limit(1)
    ).first()
    return session.get(Sentence, rows[0]) if rows else None


def _sentence_payload(session: Session, s: Sentence) -> dict:
    from ..models import MediaRoot
    from .library import stream_url

    item = session.get(MediaItem, s.item_id)
    root = session.get(MediaRoot, item.root_id) if item else None
    t0, t1 = effective_times(session, s)
    identity = session.get(SentenceIdentity, s.id)
    return {
        "sentence_id": s.id,
        "item_id": s.item_id,
        "item_kind": item.kind if item else None,
        "item_available": bool(item and item.available),
        "stream_url": stream_url(item, root.slug) if item and root and item.available else None,
        "zh": s.zh,
        "en": s.en,
        "t0_ms": t0,
        "t1_ms": t1,
        "words": (s.analysis or {}).get("words", []),
        "source_revision": identity.revision if identity else 0,
    }


@router.get("/review/queue")
def review_queue(limit: int = SESSION_CAP, session: Session = Depends(get_session)):
    """Due items, oldest first. Saved items without a review_state row are
    due immediately (rung 0) — saving enrolls implicitly."""
    limit = max(1, min(limit, SESSION_CAP))
    states = {rs.saved_item_id: rs for rs in session.scalars(select(ReviewState))}
    saved = session.scalars(
        select(SavedItem).where(SavedItem.archived.is_(False)).order_by(SavedItem.created_at)
    ).all()
    now = _now()
    due: list[tuple[SavedItem, ReviewState | None]] = []
    for item in saved:
        rs = states.get(item.id)
        if rs is None:
            due.append((item, None))  # never reviewed -> due now (saving enrolls)
        elif not rs.graduated:
            due_at = rs.due_at if rs.due_at.tzinfo else rs.due_at.replace(tzinfo=timezone.utc)
            if due_at <= now:
                due.append((item, rs))
    out = []
    for item, rs in due[:limit]:
        if item.kind == "word":
            context = _fresh_context(session, item)
            if context is None:
                live = next((c.sentence_id for c in item.contexts if c.sentence_id), None)
                context = session.get(Sentence, live) if live else None
            mode = "context"
        else:
            live = next((c.sentence_id for c in item.contexts if c.sentence_id), None)
            context = session.get(Sentence, live) if live else None
            mode = "listen"
        payload = _sentence_payload(session, context) if context else None
        if item.kind == "word" and payload and not any(w.get("lex") == item.lexeme_id for w in payload["words"]) and item.surface not in payload["zh"]:
            payload = None  # Source edits must not silently test a different word.
        if payload is None:
            snap = next((c.snapshot for c in item.contexts if (c.snapshot or {}).get("zh")), None)
            if snap:
                payload = {"sentence_id": None, "item_id": snap.get("item_id"),
                           "item_kind": None, "item_available": False, "stream_url": None,
                           "zh": snap["zh"], "en": snap.get("en"),
                           "t0_ms": snap.get("t0_ms", 0), "t1_ms": snap.get("t1_ms", 0),
                           "words": (snap.get("analysis") or {}).get("words", [])}
        lex = session.get(Lexeme, item.lexeme_id) if item.lexeme_id else None
        senses = session.scalars(select(Sense).where(Sense.lexeme_id == item.lexeme_id)
                                 .order_by(Sense.ord).limit(4)).all() if lex else []
        contextual_meaning = next((word.get("meaning") for word in (payload or {}).get("words", []) if word.get("lex") == item.lexeme_id), None)
        out.append({
            "saved_item_id": item.id,
            "kind": item.kind,
            "surface": item.surface,
            "lexeme_id": item.lexeme_id,
            "mode": mode,
            "rung": rs.rung if rs else 0,
            "streak": rs.streak if rs else 0,
            "context": payload,
            "answer": {"pinyin": item.selected_reading or next((w.get("reading") for w in (payload or {}).get("words", [])
                                if w.get("lex") == item.lexeme_id and w.get("reading")), lex.pinyin if lex else None),
                       "senses": ([{"py": item.selected_reading, "defs": [item.selected_meaning]}]
                                  if item.selected_meaning else [{"py": None, "defs": [contextual_meaning]}] if contextual_meaning else
                                  [{"py": sense.pinyin, "defs": sense.glosses} for sense in senses])},
        })
    return {"due": len(due), "items": out}


class OutcomeIn(BaseModel):
    result: str  # 'pass' | 'fail'
    mode: str | None = None
    request_uuid: str | None = Field(default=None, max_length=64)
    task: str | None = None
    assistance: str = "unknown"
    sentence_id: int | None = None
    source_revision: int | None = None
    context_zh: str | None = Field(default=None, max_length=20000)


@router.post("/review/{saved_item_id}/outcome")
def review_outcome(saved_item_id: int, body: OutcomeIn, session: Session = Depends(get_session)):
    if body.result not in ("pass", "fail"):
        raise HTTPException(400, "result must be pass|fail")
    item = session.get(SavedItem, saved_item_id)
    if item is None:
        raise HTTPException(404)
    now = _now()
    event_uuid = f"review:{saved_item_id}:{body.request_uuid}" if body.request_uuid else None
    # The write obtains SQLite's writer lock before the eligibility check.
    # Concurrent tabs cannot both advance the same due item.
    session.execute(sqlite_insert(ReviewState).values(
        saved_item_id=saved_item_id, rung=0, passes=0, fails=0, streak=0,
        graduated=False, due_at=now, updated_at=now,
    ).on_conflict_do_nothing(index_elements=["saved_item_id"]))
    if event_uuid:
        previous = session.scalar(select(Event).where(Event.client_uuid == event_uuid))
        if previous is not None:
            outcome = previous.data["outcome"]
            session.rollback()
            return outcome
    if item.archived:
        session.rollback()
        raise HTTPException(409, "This item is archived. Refresh the review queue.")
    claimed = session.execute(update(ReviewState).where(
        ReviewState.saved_item_id == saved_item_id,
        ReviewState.due_at <= now, ReviewState.graduated.is_(False),
    ).values(updated_at=now)).rowcount
    if not claimed:
        session.rollback()
        raise HTTPException(409, "This review has already been completed or is not due yet.")
    rs = session.get(ReviewState, saved_item_id, populate_existing=True)
    if body.result == "pass":
        rs.passes += 1
        rs.streak += 1
        if rs.streak > len(LADDER_DAYS):
            # Initial practice followed by successful 1d, 3d, and 7d reviews.
            rs.graduated = True
        else:
            rs.rung = min(rs.streak - 1, len(LADDER_DAYS) - 1)
    else:
        rs.fails += 1
        rs.streak = 0
        rs.rung = max(0, rs.rung - 1)
    rs.due_at = now + timedelta(days=LADDER_DAYS[min(rs.rung, len(LADDER_DAYS) - 1)])
    rs.updated_at = now

    exported = session.scalar(
        select(AnkiLink.note_id).where(AnkiLink.saved_item_id == saved_item_id)
    )
    suggest_drop = rs.fails >= 3 and rs.rung == 0
    outcome = {
        "result": body.result,
        "rung": rs.rung,
        "graduated": rs.graduated,
        "already_in_anki": exported is not None,
        "suggest_drop": suggest_drop,
        "next_due_days": LADDER_DAYS[min(rs.rung, len(LADDER_DAYS) - 1)],
    }
    event = Event(
        type="review_outcome", lexeme_id=item.lexeme_id, study_mode=body.mode or "review",
        client_uuid=event_uuid,
        data={"saved_item_id": saved_item_id, "result": body.result,
              "rung": rs.rung, "outcome": outcome,
              "reading": item.selected_reading, "meaning": item.selected_meaning,
              "task": body.task, "assistance": body.assistance},
    )
    session.add(event)
    session.flush()
    from ..models import LearningEvidence
    task = body.task if body.task in ("reading_recall", "listening_recall", "meaning_recall") else "unspecified_recall"
    session.add(LearningEvidence(event_id=event.id, lexeme_id=item.lexeme_id,
        ts=now, task=task, method="self_report",
        assistance=body.assistance if body.assistance in ("none_reported", "hinted") else "unknown",
        score=1.0 if body.result == "pass" else 0.0,
        scope={"saved_item_id": item.id, "reading": item.selected_reading,
               "meaning": item.selected_meaning, "sentence_id": body.sentence_id,
               "source_revision": body.source_revision, "context_zh": body.context_zh,
               "delayed": rs.passes+rs.fails > 1,
               "limitation": "Self-graded; does not establish whole-word mastery"}))
    session.commit()
    return outcome
