"""DB-backed job queue. The job table doubles as the admin job dashboard."""

from __future__ import annotations

from typing import Callable

from sqlalchemy import select
from sqlalchemy.orm import Session

from ..models import Job

HANDLERS: dict[str, Callable] = {}


def handler(name: str):
    def register(fn):
        HANDLERS[name] = fn
        return fn

    return register


def enqueue(
    session: Session, type_: str, payload: dict | None = None,
    priority: int = 0, dedupe: bool = True,
) -> Job | None:
    """Queue a job; identical (type, payload) already queued/running is a no-op."""
    if dedupe:
        dup = session.scalar(
            select(Job).where(
                Job.type == type_, Job.payload == payload, Job.status.in_(("queued", "running"))
            )
        )
        if dup is not None:
            return None
    job = Job(type=type_, payload=payload, priority=priority)
    session.add(job)
    session.commit()
    return job
