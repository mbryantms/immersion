"""Anki bridge endpoints: known-word import, export preview/commit."""

from __future__ import annotations

from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from ..db import get_session
from ..jobs import enqueue
from ..models import KnowledgeState, Setting

router = APIRouter()


class ImportIn(BaseModel):
    query: str | None = None
    field: str | None = None
    mature_days: int = 21


@router.post("/anki/import-known")
def import_known(body: ImportIn, session: Session = Depends(get_session)):
    payload = {"mature_days": body.mature_days}
    if body.query:
        payload["query"] = body.query
    if body.field:
        payload["field"] = body.field
    job = enqueue(session, "anki_import_known", payload)
    return {"queued": job is not None, "job_id": job.id if job else None}


@router.get("/anki/status")
def anki_status(session: Session = Depends(get_session)):
    last = session.get(Setting, "anki_last_import")
    last_export = session.get(Setting, "anki_last_export")
    counts = dict(
        session.execute(
            select(KnowledgeState.state, func.count()).group_by(KnowledgeState.state)
        ).all()
    )
    return {
        "last_import": last.value if last else None,
        "last_export": last_export.value if last_export else None,
        "state_counts": counts,
    }
