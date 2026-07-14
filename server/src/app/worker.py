"""Single worker process: claims queued jobs one at a time (which also
serializes all heavy model work on this machine), runs the handler, records
the outcome. `python -m app.worker`."""

from __future__ import annotations

import json
import logging
import time
import traceback
from datetime import datetime, timezone

from sqlalchemy import select

from . import db
from .config import settings
from .jobs import HANDLERS
from .models import Job

log = logging.getLogger("worker")


def claim_next(session) -> Job | None:
    job = session.scalars(
        select(Job).where(Job.status == "queued").order_by(Job.priority.desc(), Job.id).limit(1)
    ).first()
    if job is None:
        return None
    job.status = "running"
    job.attempts += 1
    job.started_at = datetime.now(timezone.utc)
    session.commit()
    return job


def run_one(session, job: Job) -> None:
    def progress(msg: str) -> None:
        job.progress = msg
        session.commit()

    handler = HANDLERS.get(job.type)
    try:
        if handler is None:
            raise RuntimeError(f"unknown job type {job.type!r}")
        result = handler(session, job.payload or {}, progress)
        job.status = "done"
        job.progress = json.dumps(result, ensure_ascii=False, default=str)[:500]
    except Exception:
        session.rollback()
        job.status = "failed"
        job.error = traceback.format_exc()[-4000:]
        log.exception("job %s (%s) failed", job.id, job.type)
    job.finished_at = datetime.now(timezone.utc)
    session.commit()


def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s %(message)s")
    db.init_engine()
    from .jobs import handlers  # noqa: F401 — registers HANDLERS
    from .dictdata import import_dictionary

    with db.SessionLocal() as session:
        # crash recovery: jobs stuck 'running' from a dead worker go back to queued
        for job in session.scalars(select(Job).where(Job.status == "running")):
            job.status = "queued" if job.attempts < 3 else "failed"
            job.error = job.error or "worker restarted mid-job"
        session.commit()
        imported = import_dictionary(session)
        if not imported.get("skipped"):
            log.info("dictionary imported: %s", imported)
        from .dictdata import import_examples, import_word_extras

        for result in (import_word_extras(session), import_examples(session)):
            if not result.get("skipped"):
                log.info("word extras: %s", result)

    log.info("worker up; polling every %.1fs", settings.poll_interval)
    last_anki_check = 0.0
    while True:
        with db.SessionLocal() as session:
            # opportunistic nightly Anki read-sync (Anki desktop must be open,
            # so probe cheaply every ~10min and enqueue when the import is stale)
            if time.time() - last_anki_check > 600:
                last_anki_check = time.time()
                _maybe_sync_anki(session)
            job = claim_next(session)
            if job is None:
                time.sleep(settings.poll_interval)
                continue
            log.info("job %s: %s %s", job.id, job.type, job.payload)
            run_one(session, job)


def _maybe_sync_anki(session) -> None:
    from datetime import timedelta

    from .jobs import enqueue
    from .models import Setting

    last = session.get(Setting, "anki_last_import")
    if last and (last.value or {}).get("at"):
        age = datetime.now(timezone.utc) - datetime.fromisoformat(last.value["at"])
        if age < timedelta(hours=24):
            return
    try:
        import httpx

        httpx.post(settings.anki_url, json={"action": "version", "version": 6}, timeout=2)
    except Exception:
        return  # Anki desktop not open; try again later
    enqueue(session, "anki_import_known", {})


if __name__ == "__main__":
    main()
