"""Job queue API — doubles as the admin dashboard data source."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..db import get_session
from ..jobs import enqueue
from ..models import Job

router = APIRouter()

ALLOWED = {"scan_all", "scan_root", "ingest_item", "anki_import_known",
           "whisper_align", "translate_item", "anki_export", "fts_backfill"}


class JobIn(BaseModel):
    type: str
    payload: dict | None = None


def _job_out(j: Job) -> dict:
    return {
        "id": j.id, "type": j.type, "payload": j.payload, "status": j.status,
        "attempts": j.attempts, "progress": j.progress, "error": j.error,
        "created_at": j.created_at, "started_at": j.started_at, "finished_at": j.finished_at,
    }


@router.get("/jobs")
def list_jobs(status: str | None = None, limit: int = 100, session: Session = Depends(get_session)):
    q = select(Job).order_by(Job.id.desc()).limit(min(limit, 500))
    if status:
        q = q.where(Job.status == status)
    jobs = session.scalars(q).all()
    counts = {
        s: session.scalar(select(Job.id).where(Job.status == s).limit(1)) is not None
        for s in ("queued", "running")
    }
    return {"jobs": [_job_out(j) for j in jobs], "active": counts["queued"] or counts["running"]}


@router.post("/jobs")
def create_job(body: JobIn, session: Session = Depends(get_session)):
    if body.type not in ALLOWED:
        raise HTTPException(400, f"type must be one of {sorted(ALLOWED)}")
    job = enqueue(session, body.type, body.payload)
    if job is None:
        return {"deduped": True}
    return _job_out(job)


@router.post("/jobs/{job_id}/retry")
def retry_job(job_id: int, session: Session = Depends(get_session)):
    job = session.get(Job, job_id)
    if job is None:
        raise HTTPException(404)
    if job.status != "failed":
        raise HTTPException(400, "only failed jobs can be retried")
    job.status = "queued"
    job.error = None
    session.commit()
    return _job_out(job)
