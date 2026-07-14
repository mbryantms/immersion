"""Contextual review queue: triage funnel, not an SRS (Anki owns retention).

Fixed 1d -> 3d -> 7d ladder; fail drops a rung. Word reviews prefer a fresh
concordance sentence over the saved context (variability); sentence reviews
are dictation (scored client-side, same LCS as lingua/diff.py). Graduation
(clearing 7d, or two straight passes at the top rung) surfaces the item for
the Anki export tray."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import func, select
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
)

router = APIRouter()

LADDER_DAYS = [1, 3, 7]
SESSION_CAP = 20


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _fresh_context(session: Session, item: SavedItem) -> Sentence | None:
    """A concordance sentence that is NOT one of the saved contexts — later
    reviews should retrieve meaning in a new setting, not recognize the card."""
    if not item.lexeme_id:
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
    return {
        "sentence_id": s.id,
        "item_id": s.item_id,
        "item_kind": item.kind if item else None,
        "item_available": bool(item and item.available),
        "stream_url": stream_url(item, root.slug) if item and root else None,
        "zh": s.zh,
        "en": s.en,
        "t0_ms": s.t0_ms,
        "t1_ms": s.t1_ms,
        "words": (s.analysis or {}).get("words", []),
    }


@router.get("/review/queue")
def review_queue(limit: int = SESSION_CAP, session: Session = Depends(get_session)):
    """Due items, oldest first. Saved items without a review_state row are
    due immediately (rung 0) — saving enrolls implicitly."""
    limit = min(limit, SESSION_CAP)
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
            mode = "dictation"
        out.append({
            "saved_item_id": item.id,
            "kind": item.kind,
            "surface": item.surface,
            "lexeme_id": item.lexeme_id,
            "mode": mode,
            "rung": rs.rung if rs else 0,
            "streak": rs.streak if rs else 0,
            "context": _sentence_payload(session, context) if context else None,
        })
    return {"due": len(due), "items": out}


class OutcomeIn(BaseModel):
    result: str  # 'pass' | 'fail'
    mode: str | None = None
    score: float | None = None  # dictation score, informational


@router.post("/review/{saved_item_id}/outcome")
def review_outcome(saved_item_id: int, body: OutcomeIn, session: Session = Depends(get_session)):
    if body.result not in ("pass", "fail"):
        raise HTTPException(400, "result must be pass|fail")
    item = session.get(SavedItem, saved_item_id)
    if item is None:
        raise HTTPException(404)
    rs = session.get(ReviewState, saved_item_id)
    if rs is None:
        rs = ReviewState(saved_item_id=saved_item_id, rung=0, passes=0, fails=0,
                         streak=0, graduated=False)
        session.add(rs)

    now = _now()
    if body.result == "pass":
        rs.passes += 1
        rs.streak += 1
        # graduate on clearing the 7d rung, or two straight passes anywhere
        if rs.rung >= len(LADDER_DAYS) - 1 or rs.streak >= 2:
            rs.graduated = True
        else:
            rs.rung += 1
    else:
        rs.fails += 1
        rs.streak = 0
        rs.rung = max(0, rs.rung - 1)
    rs.due_at = now + timedelta(days=LADDER_DAYS[min(rs.rung, len(LADDER_DAYS) - 1)])
    rs.updated_at = now

    session.add(Event(
        type="review_outcome", lexeme_id=item.lexeme_id, study_mode=body.mode or "review",
        data={"saved_item_id": saved_item_id, "result": body.result, "score": body.score,
              "rung": rs.rung},
    ))
    session.commit()

    exported = session.scalar(
        select(AnkiLink.note_id).where(AnkiLink.saved_item_id == saved_item_id)
    )
    suggest_drop = rs.fails >= 3 and rs.rung == 0
    return {
        "rung": rs.rung,
        "graduated": rs.graduated,
        "already_in_anki": exported is not None,
        "suggest_drop": suggest_drop,
        "next_due_days": LADDER_DAYS[min(rs.rung, len(LADDER_DAYS) - 1)],
    }
