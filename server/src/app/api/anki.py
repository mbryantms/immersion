"""Anki bridge endpoints: known-word import, export preview/commit."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from ..anki.connect import AnkiError
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
    counts = dict(session.execute(
        select(KnowledgeState.state, func.count()).group_by(KnowledgeState.state)
    ).all())
    return {
        "last_import": last.value if last else None,
        "last_export": last_export.value if last_export else None,
        "state_counts": counts,
    }


class PreviewIn(BaseModel):
    saved_item_ids: list[int]


@router.post("/anki/export-preview")
def export_preview(body: PreviewIn, session: Session = Depends(get_session)):
    """Interactive: field building + collection-wide dup detection, no media."""
    from ..anki.export import build_preview

    try:
        return build_preview(session, body.saved_item_ids)
    except AnkiError as e:
        raise HTTPException(503, str(e)) from e


class ExportEntry(BaseModel):
    saved_item_id: int
    fields: dict[str, str]
    allow_duplicate: bool = False
    include_media: bool = True


class ExportIn(BaseModel):
    entries: list[ExportEntry]


@router.post("/anki/export")
def export(body: ExportIn, session: Session = Depends(get_session)):
    """Commit runs in the worker — clips/frames/TTS take seconds per item."""
    if not body.entries:
        raise HTTPException(400, "no entries")
    job = enqueue(session, "anki_export", {"entries": [e.model_dump() for e in body.entries]})
    return {"queued": job is not None, "job_id": job.id if job else None}
