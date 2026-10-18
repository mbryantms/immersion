"""Configurable Anki preflight, SQL-backed graduate inbox and durable handoff."""

from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, ConfigDict, Field, field_validator
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from ..anki import handoff
from ..anki.connect import AnkiError
from ..anki.profile import Profile, current, digest, preflight
from ..db import get_session
from ..models import AnkiLink, Event, ExportAttempt, Job, ReviewState, SavedItem, Setting

router = APIRouter()


def remote(call):
    try:
        return call()
    except AnkiError as error:
        raise HTTPException(503, str(error)) from error
    except handoff.HandoffConflict as error:
        raise HTTPException(409, str(error)) from error


@router.get("/anki/export-profile")
def get_profile(session: Session = Depends(get_session)):
    profile = current(session)
    return {"profile": profile.model_dump(), "profile_hash": digest(profile.model_dump())}


@router.post("/anki/preflight")
def check_profile(body: Profile):
    return remote(lambda: preflight(body))


@router.put("/anki/export-profile")
def save_profile(body: Profile, session: Session = Depends(get_session)):
    check = remote(lambda: preflight(body))
    if not check["ok"]:
        raise HTTPException(
            422, {"message": "Anki configuration needs attention", "errors": check["errors"]}
        )
    session.merge(Setting(key="anki-export-profile", value=body.model_dump()))
    session.add(
        Event(type="anki_export_profile_changed", data={"profile_hash": check["profile_hash"]})
    )
    session.commit()
    return get_profile(session)


class Preview(BaseModel):
    model_config = ConfigDict(extra="forbid")
    saved_item_ids: list[int] = Field(min_length=1, max_length=50)

    @field_validator("saved_item_ids")
    @classmethod
    def unique(cls, ids):
        if len(set(ids)) != len(ids) or any(value <= 0 for value in ids):
            raise ValueError("Select distinct saved card IDs")
        return ids


@router.post("/anki/export-preview")
def preview(body: Preview, session: Session = Depends(get_session)):
    return remote(lambda: handoff.preview(session, body.saved_item_ids))


class Entry(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)
    saved_item_id: int = Field(gt=0)
    source_hash: str = Field(pattern=r"^[a-f0-9]{64}$")
    meaning: str = Field(min_length=1, max_length=2000)
    allow_duplicate: bool = False
    include_media: bool = True


class Submission(BaseModel):
    model_config = ConfigDict(extra="forbid")
    request_uuid: UUID
    profile_hash: str = Field(pattern=r"^[a-f0-9]{64}$")
    entries: list[Entry] = Field(min_length=1, max_length=50)

    @field_validator("entries")
    @classmethod
    def unique(cls, entries):
        if len({entry.saved_item_id for entry in entries}) != len(entries):
            raise ValueError("A card may appear only once per submission")
        return entries


@router.post("/anki/export")
def submit(body: Submission, session: Session = Depends(get_session)):
    return remote(lambda: handoff.submit(session, body))


def inbox_query(deferred):
    return (
        select(SavedItem)
        .join(ReviewState, ReviewState.saved_item_id == SavedItem.id)
        .where(
            ReviewState.graduated.is_(True),
            SavedItem.archived.is_(False),
            SavedItem.export_deferred.is_(deferred),
        )
        .where(~select(AnkiLink.id).where(AnkiLink.saved_item_id == SavedItem.id).exists())
    )


@router.get("/anki/inbox")
def inbox(
    view: str = Query(default="ready", pattern="^(ready|deferred)$"),
    before_id: int | None = None,
    limit: int = Query(default=30, ge=1, le=50),
    session: Session = Depends(get_session),
):
    counts = {
        name: session.scalar(select(func.count()).select_from(inbox_query(value).subquery()))
        for name, value in (("ready", False), ("deferred", True))
    }
    query = inbox_query(view == "deferred")
    if before_id is not None:
        query = query.where(SavedItem.id < before_id)
    items = session.scalars(query.order_by(SavedItem.id.desc()).limit(limit + 1)).all()
    more = len(items) > limit
    items = items[:limit]
    ids = [item.id for item in items]
    latest_ids = (
        select(func.max(ExportAttempt.id))
        .where(ExportAttempt.saved_item_id.in_(ids))
        .group_by(ExportAttempt.saved_item_id)
    )
    attempts = {
        row.saved_item_id: row
        for row in session.scalars(select(ExportAttempt).where(ExportAttempt.id.in_(latest_ids)))
    }
    return {
        "counts": counts,
        "items": [
            {
                "id": item.id,
                "surface": item.surface or "Saved sentence",
                "kind": item.kind,
                "selected_reading": item.selected_reading,
                "selected_meaning": item.selected_meaning,
                "attempt_id": attempts[item.id].id if item.id in attempts else None,
                "export_status": attempts[item.id].status if item.id in attempts else None,
            }
            for item in items
        ],
        "next_cursor": items[-1].id if more else None,
    }


class Defer(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)
    deferred: bool


@router.put("/anki/inbox/{saved_id}")
def defer(saved_id: int, body: Defer, session: Session = Depends(get_session)):
    item = session.get(SavedItem, saved_id)
    if not item:
        raise HTTPException(404)
    if item.export_deferred != body.deferred:
        item.export_deferred = body.deferred
        session.add(
            Event(
                type="anki_export_deferred" if body.deferred else "anki_export_restored",
                data={"saved_item_id": saved_id},
            )
        )
    session.commit()
    return {"id": saved_id, "deferred": item.export_deferred}


def attempt_out(row, is_latest=True):
    return {
        "id": row.id,
        "is_latest": is_latest,
        "saved_item_id": row.saved_item_id,
        "original_saved_item_id": row.original_saved_item_id,
        "surface": row.snapshot["fields"].get("Simplified", "Saved card"),
        "fields": row.snapshot["fields"],
        "profile": row.snapshot["profile"],
        "source_revision": row.snapshot.get("source_revision"),
        "status": row.status,
        "note_id": row.note_id,
        "error": row.error,
        "warnings": row.warnings,
        "export_tag": row.export_key,
        "created_at": row.created_at,
    }


def latest_ids(session, rows):
    ids = [row.saved_item_id for row in rows if row.saved_item_id is not None]
    return dict(
        session.execute(
            select(ExportAttempt.saved_item_id, func.max(ExportAttempt.id))
            .where(ExportAttempt.saved_item_id.in_(ids))
            .group_by(ExportAttempt.saved_item_id)
        ).all()
    )


@router.get("/anki/exports")
def exports(
    before_job_id: int | None = None,
    include_attempt_id: int | None = None,
    session: Session = Depends(get_session),
):
    query = select(ExportAttempt.job_id).distinct()
    if before_job_id is not None:
        query = query.where(ExportAttempt.job_id < before_job_id)
    ids = list(session.scalars(query.order_by(ExportAttempt.job_id.desc()).limit(21)))
    more = len(ids) > 20
    ids = ids[:20]
    cursor = ids[-1] if more else None
    if include_attempt_id is not None:
        selected = session.get(ExportAttempt, include_attempt_id)
        if selected and selected.job_id not in ids:
            ids.insert(0, selected.job_id)
    rows = session.scalars(
        select(ExportAttempt).where(ExportAttempt.job_id.in_(ids)).order_by(ExportAttempt.id)
    ).all()
    latest = latest_ids(session, rows)
    jobs = {job.id: job for job in session.scalars(select(Job).where(Job.id.in_(ids)))}
    return {
        "batches": [
            {
                "job_id": job_id,
                "status": jobs[job_id].status,
                "error": jobs[job_id].error
                and "Worker stopped. Retry or re-preview the affected cards.",
                "items": [
                    attempt_out(
                        row, row.saved_item_id is None or latest.get(row.saved_item_id) == row.id
                    )
                    for row in rows
                    if row.job_id == job_id
                ],
            }
            for job_id in ids
        ],
        "next_cursor": cursor,
    }


@router.get("/anki/exports/{job_id}")
def export_detail(job_id: int, session: Session = Depends(get_session)):
    job = session.get(Job, job_id)
    if not job or job.type != "anki_export":
        raise HTTPException(404)
    rows = session.scalars(
        select(ExportAttempt).where(ExportAttempt.job_id == job_id).order_by(ExportAttempt.id)
    ).all()
    return {
        "job_id": job.id,
        "status": job.status,
        "progress": job.progress if job.status in {"queued", "running"} else None,
        "items": [attempt_out(row) for row in rows],
    }


def terminal_attempt(session, attempt_id):
    row = session.get(ExportAttempt, attempt_id)
    if row is None:
        raise HTTPException(404)
    job = session.get(Job, row.job_id)
    if job.status in {"queued", "running"}:
        raise HTTPException(409, "Wait for the active export to finish")
    return row


@router.post("/anki/export-attempts/{attempt_id}/reconcile")
def reconcile(attempt_id: int, session: Session = Depends(get_session)):
    row = terminal_attempt(session, attempt_id)
    found = remote(lambda: handoff.reconcile(session, row))
    if not found and row.status == "uncertain":
        row.error = (
            "No note with this export tag was found. Check Anki before allowing another add."
        )
        session.commit()
    return attempt_out(row)


class Retry(BaseModel):
    model_config = ConfigDict(extra="forbid")
    request_uuid: UUID
    confirm_no_note: bool = False


@router.post("/anki/export-attempts/{attempt_id}/retry")
def retry(attempt_id: int, body: Retry, session: Session = Depends(get_session)):
    handoff.writer_lock(session)
    payload_hash = digest({"attempt_id": attempt_id, **body.model_dump(mode="json")})
    event = session.scalar(select(Event).where(Event.client_uuid == str(body.request_uuid)))
    if event:
        if event.type != "anki_export_retry" or event.data.get("payload_hash") != payload_hash:
            raise HTTPException(409, "Request identifier already used for another action")
        return {"job_id": event.data["job_id"]}
    row = terminal_attempt(session, attempt_id)
    if not row.saved_item_id:
        raise HTTPException(409, "This saved card was removed; its export history is retained")
    last = handoff.latest(session, row.saved_item_id)
    if last.id != row.id or row.status not in {"error", "uncertain", "queued"}:
        raise HTTPException(
            409, "This attempt was resolved or superseded. Reload its current status."
        )
    # An error before addNote is safely retryable. Uncertainty requires an
    # explicit check in Anki, while a reconcile-only action never adds a note.
    if row.status == "uncertain" and not body.confirm_no_note:
        raise HTTPException(409, "Check Anki and explicitly confirm before allowing another add")
    job = Job(type="anki_export", payload={}, priority=5)
    session.add(job)
    session.flush()
    snapshot = {**row.snapshot, "allow_add": True}
    new = ExportAttempt(
        job_id=job.id,
        saved_item_id=row.saved_item_id,
        original_saved_item_id=row.original_saved_item_id,
        export_key=row.export_key,
        snapshot=snapshot,
        status="queued",
    )
    session.add(new)
    session.flush()
    job.payload = {"export_ids": [new.id]}
    session.add(
        Event(
            type="anki_export_retry",
            client_uuid=str(body.request_uuid),
            data={
                "payload_hash": payload_hash,
                "job_id": job.id,
                "previous_attempt": row.id,
                "confirm_no_note": body.confirm_no_note,
            },
        )
    )
    session.commit()
    return {"job_id": job.id}
