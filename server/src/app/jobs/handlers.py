"""Job handlers. Imported only by the worker — HanLP/torch stay out of the API
process. Each handler gets (session, payload, progress)."""

from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.orm import Session

from ..models import MediaRoot
from . import enqueue, handler


@handler("scan_root")
def scan_root(session: Session, payload: dict, progress) -> dict:
    root_id = payload["root_id"]
    root = session.get(MediaRoot, root_id)
    if root is None or not root.enabled:
        return {"skipped": True}
    # both scans enqueue ingest_item incrementally themselves (crash-safe)
    if root.kind == "podcast":
        from ..ingest.podcast import scan_podcast_root

        result = scan_podcast_root(session, root, progress)
    else:
        from ..ingest.scanner import scan_video_root

        result = scan_video_root(session, root, progress)
    root.last_scan_at = datetime.now(timezone.utc)
    session.commit()
    return result["stats"]


@handler("scan_all")
def scan_all(session: Session, payload: dict, progress) -> dict:
    roots = session.scalars(select(MediaRoot).where(MediaRoot.enabled)).all()
    for root in roots:
        enqueue(session, "scan_root", {"root_id": root.id})
    return {"roots": len(roots)}


@handler("ingest_item")
def ingest_item_handler(session: Session, payload: dict, progress) -> dict:
    from ..models import MediaItem

    item = session.get(MediaItem, payload["item_id"])
    if item is not None and item.kind == "audio":
        from ..ingest.podcast import ingest_podcast_item

        ingest_podcast_item(session, payload["item_id"], progress)
    else:
        from ..ingest.analysis import ingest_item

        ingest_item(session, payload["item_id"], progress)
    return {"item_id": payload["item_id"]}


@handler("whisper_align")
def whisper_align(session: Session, payload: dict, progress) -> dict:
    from ..ingest.podcast import whisper_align_item

    return whisper_align_item(session, payload["item_id"], progress)


@handler("whisper_transcribe")
def whisper_transcribe(session: Session, payload: dict, progress) -> dict:
    from ..ingest.transcribe import whisper_transcribe_item

    return whisper_transcribe_item(session, payload["item_id"], progress)


@handler("remux_item")
def remux_item_handler(session: Session, payload: dict, progress) -> dict:
    from ..ingest.remux import remux_item

    return remux_item(session, payload["item_id"], progress)


@handler("translate_item")
def translate_item_handler(session: Session, payload: dict, progress) -> dict:
    from ..ai.tasks import translate_item

    return translate_item(session, payload["item_id"], progress)


@handler("anki_import_known")
def anki_import_known(session: Session, payload: dict, progress) -> dict:
    from ..anki.import_known import import_known

    return import_known(session, progress=progress, **payload)


@handler("anki_export")
def anki_export(session: Session, payload: dict, progress) -> dict:
    from ..anki.export import export_items

    return export_items(session, payload["entries"], progress)


@handler("fts_backfill")
def fts_backfill(session: Session, payload: dict, progress) -> dict:
    """Rebuild sentence_fts from scratch (one-shot after the FTS migration)."""
    from sqlalchemy import text

    from ..ingest.analysis import write_fts
    from ..models import Sentence

    session.execute(text("DELETE FROM sentence_fts"))
    ids = [i for (i,) in session.execute(select(Sentence.id).order_by(Sentence.id))]
    for i in range(0, len(ids), 500):
        batch = session.scalars(select(Sentence).where(Sentence.id.in_(ids[i : i + 500]))).all()
        write_fts(session, batch)
        session.commit()
        progress(f"indexed {min(i + 500, len(ids))}/{len(ids)}")
    return {"sentences": len(ids)}
