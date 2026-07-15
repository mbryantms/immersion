"""Mutable learner-state overlay: lexeme knowledge states."""

from __future__ import annotations

from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..db import get_session
from ..models import Event, KnowledgeState, Lexeme, LexemeStats, SavedItem, Setting, TokenOccurrence

router = APIRouter()

STATES = {"new", "learning", "familiar", "known", "ignored"}


def _clear_manual_state(lexeme_id: int, session: Session) -> dict:
    """Remove a manual override and reveal the strongest remaining evidence.

    Anki evidence outranks the derived Learning state created by an active save.
    If neither exists the row is removed, making the effective state New.
    """
    ks = session.get(KnowledgeState, lexeme_id)
    if ks is None or ks.source != "manual":
        return {
            "lexeme_id": lexeme_id,
            "state": ks.state if ks else "new",
            "source": ks.source if ks else None,
            "cleared": False,
        }

    previous_state = ks.state
    last_import = session.get(Setting, "anki_last_import")
    mature_days = int((last_import.value or {}).get("mature_days", 21)) if last_import else 21
    interval = ks.anki_interval_days
    saved = session.scalar(
        select(SavedItem.id).where(
            SavedItem.kind == "word",
            SavedItem.lexeme_id == lexeme_id,
            SavedItem.archived.is_(False),
        )
    )
    now = datetime.now(timezone.utc)
    if interval is not None and interval >= 1:
        ks.state = "known" if interval >= mature_days else "learning"
        ks.source = "anki"
        ks.updated_at = now
        effective_state, effective_source = ks.state, ks.source
    elif saved is not None:
        ks.state = "learning"
        ks.source = "derived"
        ks.updated_at = now
        effective_state, effective_source = ks.state, ks.source
    else:
        session.delete(ks)
        effective_state, effective_source = "new", None

    session.add(Event(
        type="knowledge_reset",
        lexeme_id=lexeme_id,
        data={"previous_state": previous_state,
              "effective_state": effective_state, "effective_source": effective_source},
    ))
    return {
        "lexeme_id": lexeme_id,
        "state": effective_state,
        "source": effective_source,
        "cleared": True,
    }


@router.get("/knowledge")
def get_knowledge(item_id: int, session: Session = Depends(get_session)):
    """lexeme_id -> state for every lexeme occurring in the item, plus which
    lexemes have an active save. The overlay the player paints tokens with."""
    lex_ids = select(TokenOccurrence.lexeme_id).where(TokenOccurrence.item_id == item_id).distinct()
    states = session.scalars(
        select(KnowledgeState).where(KnowledgeState.lexeme_id.in_(lex_ids))
    ).all()
    saved = session.scalars(
        select(SavedItem.lexeme_id).where(
            SavedItem.lexeme_id.in_(lex_ids), SavedItem.archived.is_(False)
        )
    ).all()
    return {
        "states": {ks.lexeme_id: ks.state for ks in states},
        "saved": sorted(set(saved)),
    }


class StateIn(BaseModel):
    state: str


@router.put("/knowledge/{lexeme_id}")
def put_knowledge(lexeme_id: int, body: StateIn, session: Session = Depends(get_session)):
    if body.state not in STATES:
        raise HTTPException(400, f"state must be one of {sorted(STATES)}")
    if session.get(Lexeme, lexeme_id) is None:
        raise HTTPException(404, "lexeme not found")
    # `new` means "remove my decision", not a permanent manual override that
    # would mask later Anki imports or an active learning-queue save.
    if body.state == "new":
        result = _clear_manual_state(lexeme_id, session)
        session.commit()
        return result

    ks = session.get(KnowledgeState, lexeme_id)
    now = datetime.now(timezone.utc)
    if ks is None:
        session.add(KnowledgeState(lexeme_id=lexeme_id, state=body.state, source="manual", updated_at=now))
    else:
        ks.state, ks.source, ks.updated_at = body.state, "manual", now
    session.commit()
    return {"lexeme_id": lexeme_id, "state": body.state, "source": "manual"}


@router.delete("/knowledge/{lexeme_id}")
def clear_knowledge(lexeme_id: int, session: Session = Depends(get_session)):
    if session.get(Lexeme, lexeme_id) is None:
        raise HTTPException(404, "lexeme not found")
    result = _clear_manual_state(lexeme_id, session)
    session.commit()
    return result


@router.delete("/lexemes/{lexeme_id}/stats")
def reset_lexeme_stats(lexeme_id: int, session: Session = Depends(get_session)):
    if session.get(Lexeme, lexeme_id) is None:
        raise HTTPException(404, "lexeme not found")
    stats = session.get(LexemeStats, lexeme_id)
    previous = None
    if stats is not None:
        previous = {
            "encounters": stats.encounters,
            "lookups": stats.lookups,
            "distinct_items": stats.distinct_items,
            "first_seen": stats.first_seen.isoformat() if stats.first_seen else None,
            "last_seen": stats.last_seen.isoformat() if stats.last_seen else None,
        }
        session.delete(stats)
    session.add(Event(type="lexeme_stats_reset", lexeme_id=lexeme_id, data={"previous": previous}))
    session.commit()
    return {"lexeme_id": lexeme_id, "reset": stats is not None}
