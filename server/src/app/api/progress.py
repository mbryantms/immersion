"""Playback position + subtitle mode, restored across sessions."""

from __future__ import annotations

from datetime import datetime, timezone

from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlalchemy.orm import Session

from ..db import get_session
from ..models import PlaybackProgress

router = APIRouter()


class ProgressIn(BaseModel):
    position_ms: int
    duration_ms: int | None = None
    completed: bool | None = None
    subtitle_mode: str | None = None


@router.get("/progress/{item_id}")
def get_progress(item_id: int, session: Session = Depends(get_session)):
    p = session.get(PlaybackProgress, item_id)
    return {
        "item_id": item_id,
        "position_ms": p.position_ms if p else 0,
        "completed": p.completed if p else False,
        "subtitle_mode": p.subtitle_mode if p else None,
    }


@router.put("/progress/{item_id}")
def put_progress(item_id: int, body: ProgressIn, session: Session = Depends(get_session)):
    p = session.get(PlaybackProgress, item_id)
    if p is None:
        p = PlaybackProgress(item_id=item_id)
        session.add(p)
    p.position_ms = body.position_ms
    if body.duration_ms is not None:
        p.duration_ms = body.duration_ms
    if body.completed is not None:
        p.completed = body.completed
    elif p.duration_ms and body.position_ms > 0.97 * p.duration_ms:
        p.completed = True
    if body.subtitle_mode is not None:
        p.subtitle_mode = body.subtitle_mode
    p.updated_at = datetime.now(timezone.utc)
    session.commit()
    return {"ok": True}
