"""Source-bound submissions and per-note delivery with explicit uncertain outcomes."""

from datetime import datetime, timezone
import base64
import re
from uuid import uuid4

from sqlalchemy import select
from sqlalchemy.dialects.sqlite import insert

from ..models import AnkiLink, Event, ExportAttempt, Job, MediaItem, SavedItem, Setting
from . import export as media
from .connect import AnkiError, AnkiUnavailable, ac
from .profile import chinese_key, current, digest, preflight

ACTIVE = {"queued", "running", "uncertain"}


class HandoffConflict(RuntimeError):
    pass


def writer_lock(session):
    session.execute(
        insert(Setting).values(key="anki-handoff-lock", value=True).on_conflict_do_nothing()
    )


def latest(session, saved_id):
    return session.scalar(
        select(ExportAttempt)
        .where(ExportAttempt.saved_item_id == saved_id)
        .order_by(ExportAttempt.id.desc())
        .limit(1)
    )


def source(session, item, profile):
    sentence, _ = media._context(session, item)
    if sentence is not None:
        session.refresh(sentence)
    fields, meta = media._fields(session, item)
    asset = session.get(MediaItem, sentence.item_id) if sentence else None
    if asset is not None:
        session.refresh(asset)
    from ..models import SentenceIdentity
    from ..timing import effective_times

    identity = session.get(SentenceIdentity, sentence.id) if sentence else None
    if identity is not None:
        session.refresh(identity)
    path = media._media_source(session, sentence) if sentence else None
    t0, t1 = effective_times(session, sentence) if sentence else (0, 0)
    file_stat = path.stat() if path and path.is_file() else None
    context = {
        "file_signature": [file_stat.st_size, file_stat.st_mtime_ns] if file_stat else None,
        "fields": fields,
        "sentence_id": sentence.id if sentence else None,
        "source_revision": identity.revision if identity else 0,
        "fingerprint": asset.fingerprint if asset else None,
        "item_id": asset.id if asset else None,
        "t0": t0,
        "t1": t1,
        "path": str(path) if path else None,
        "kind": asset.kind if asset else None,
        "selected_reading": item.selected_reading,
        "selected_meaning": item.selected_meaning,
        "profile": profile.model_dump(),
    }
    return context, meta, digest(context)


def preview(session, saved_ids):
    profile = current(session)
    check = preflight(profile)
    if not check["ok"]:
        return {
            "deck": profile.deck,
            "model": profile.model,
            "profile_hash": check["profile_hash"],
            "preflight": check,
            "items": [],
        }
    items = {
        item.id: item
        for item in session.scalars(select(SavedItem).where(SavedItem.id.in_(saved_ids)))
    }
    links = dict(
        session.execute(
            select(AnkiLink.saved_item_id, AnkiLink.note_id).where(
                AnkiLink.saved_item_id.in_(saved_ids)
            )
        ).all()
    )
    out = []
    for saved_id in saved_ids:
        item = items.get(saved_id)
        if item is None:
            raise HandoffConflict("A selected saved card was removed. Reload the list.")
        context, meta, token = source(session, item, profile)
        fields = context["fields"]
        meta["can_clip"] = bool(
            meta["can_clip"] and context["file_signature"] and "SentenceAudio" in profile.fields
        )
        meta["can_image"] = bool(
            meta["can_image"] and context["file_signature"] and "Image" in profile.fields
        )
        errors = []
        if not fields[chinese_key(profile)].strip():
            errors.append(
                "The mapped Chinese text is unavailable for this card. Choose another field or source."
            )
        if item.archived:
            errors.append("Resume this suspended card before exporting")
        if item.selected_reading and "Pinyin" not in profile.fields:
            errors.append("Map Pinyin in Settings to preserve this card's selected reading")
        prior = latest(session, saved_id)
        if prior and prior.status in ACTIVE:
            errors.append(
                "An export is pending or unconfirmed. Resolve it in the export inbox first."
            )
        # JSON-quoted values protect user text from becoming Anki search syntax.
        import json

        key = chinese_key(profile)
        target = profile.fields[key]
        dup_ids = (
            ac(
                "findNotes",
                query=json.dumps(f"{target}:{fields[key]}", ensure_ascii=False),
            )
            or []
        )
        meanings = []
        if dup_ids:
            for info in ac("notesInfo", notes=dup_ids[:3]) or []:
                value = (info.get("fields", {}).get(profile.fields["Meaning"]) or {}).get(
                    "value", ""
                )
                meanings.append(re.sub(r"<[^>]+>", "", value)[:100])
        out.append(
            {
                "saved_item_id": item.id,
                "kind": item.kind,
                "fields": fields,
                **meta,
                "source_hash": token,
                "errors": errors,
                "duplicates": len(dup_ids),
                "duplicate_meanings": meanings,
                "already_exported": links.get(item.id),
            }
        )
    return {
        "deck": profile.deck,
        "model": profile.model,
        "profile_hash": check["profile_hash"],
        "preflight": check,
        "items": out,
    }


def submit(session, body):
    payload = body.model_dump(mode="json")
    payload_hash = digest(payload)
    writer_lock(session)
    replay = session.scalar(select(Event).where(Event.client_uuid == str(body.request_uuid)))
    if replay:
        if (
            replay.type != "anki_export_submitted"
            or replay.data.get("payload_hash") != payload_hash
        ):
            raise HandoffConflict("This request identifier belongs to another submission")
        return {"queued": True, "job_id": replay.data["job_id"], "replayed": True}
    profile = current(session)
    if digest(profile.model_dump()) != body.profile_hash:
        raise HandoffConflict("Anki settings changed. Refresh the preview before exporting.")
    # Run remote preflight before opening a SQLite writer transaction, then
    # reacquire and revalidate below. No long remote operation holds the DB lock.
    session.rollback()
    check = preflight(profile)
    if not check["ok"]:
        raise HandoffConflict("Anki preflight changed. Refresh the preview or open Settings.")
    writer_lock(session)
    session.expire_all()
    replay = session.scalar(select(Event).where(Event.client_uuid == str(body.request_uuid)))
    if replay:
        if (
            replay.type != "anki_export_submitted"
            or replay.data.get("payload_hash") != payload_hash
        ):
            raise HandoffConflict("This request identifier belongs to another submission")
        return {"queued": True, "job_id": replay.data["job_id"], "replayed": True}
    if digest(current(session).model_dump()) != body.profile_hash:
        raise HandoffConflict("Anki settings changed. Refresh the preview.")
    snapshots = []
    for entry in body.entries:
        item = session.get(SavedItem, entry.saved_item_id)
        if not item or item.archived:
            raise HandoffConflict("A selected card was removed or suspended")
        if session.scalar(select(AnkiLink.id).where(AnkiLink.saved_item_id == item.id)):
            raise HandoffConflict("A selected card has already been exported")
        prior = latest(session, item.id)
        if prior and prior.status in ACTIVE:
            raise HandoffConflict("A selected card already has a pending or unconfirmed export")
        context, _, token = source(session, item, profile)
        if not context["fields"][chinese_key(profile)].strip():
            raise HandoffConflict("The mapped Chinese text is unavailable for this card")
        if token != entry.source_hash:
            raise HandoffConflict(
                "Source text, reading, meaning or timing changed. Refresh the preview."
            )
        if item.selected_reading and "Pinyin" not in profile.fields:
            raise HandoffConflict("Map Pinyin to preserve the selected reading")
        fields = dict(context["fields"])
        # Meaning is the only preview edit. Other source fields remain grounded.
        fields["Meaning"] = entry.meaning.strip()
        if not fields["Meaning"]:
            raise HandoffConflict("Every exported card needs a nonblank meaning")
        context.update(
            fields=fields,
            source_hash=token,
            allow_duplicate=entry.allow_duplicate,
            include_media=entry.include_media,
            allow_add=True,
        )
        snapshots.append(
            (item, context, prior.export_key if prior else "immersion-id-" + uuid4().hex)
        )
    job = Job(type="anki_export", payload={}, priority=5)
    session.add(job)
    session.flush()
    ids = []
    for item, context, key in snapshots:
        attempt = ExportAttempt(
            job_id=job.id,
            saved_item_id=item.id,
            original_saved_item_id=item.id,
            export_key=key,
            snapshot=context,
            status="queued",
        )
        session.add(attempt)
        session.flush()
        ids.append(attempt.id)
    job.payload = {"export_ids": ids}
    session.add(
        Event(
            type="anki_export_submitted",
            client_uuid=str(body.request_uuid),
            data={"payload_hash": payload_hash, "job_id": job.id, "count": len(ids)},
        )
    )
    session.commit()
    return {"queued": True, "job_id": job.id, "replayed": False}


def _link(session, attempt, note_id):
    writer_lock(session)
    session.refresh(attempt)
    if not isinstance(note_id, int) or isinstance(note_id, bool) or note_id <= 0:
        raise AnkiUnavailable("Anki did not confirm a valid note identifier")
    if attempt.saved_item_id is None:
        # The immutable result remains visible after local removal.
        linked = None
    else:
        linked = session.scalar(
            select(AnkiLink).where(AnkiLink.saved_item_id == attempt.saved_item_id)
        )
    profile = attempt.snapshot["profile"]
    if linked is None:
        item = session.get(SavedItem, attempt.saved_item_id) if attempt.saved_item_id else None
        session.add(
            AnkiLink(
                saved_item_id=attempt.saved_item_id,
                lexeme_id=item.lexeme_id if item else None,
                note_id=note_id,
                deck=profile["deck"],
                model=profile["model"],
                fields_hash=digest(attempt.snapshot["fields"]),
                status="exported",
            )
        )
    elif linked.note_id != note_id:
        raise HandoffConflict("A different Anki note is already linked to this saved card")
    attempt.note_id = note_id
    attempt.status = "added"
    attempt.error = None
    attempt.updated_at = datetime.now(timezone.utc)
    session.add(
        Event(type="anki_export_confirmed", data={"attempt_id": attempt.id, "note_id": note_id})
    )
    session.commit()


def reconcile(session, attempt):
    ids = ac("findNotes", query=f"tag:{attempt.export_key}")
    if not isinstance(ids, list):
        raise AnkiUnavailable("Anki did not return a readable reconciliation result")
    if len(ids) > 1:
        raise HandoffConflict(
            "More than one Anki note carries this export tag. Resolve the copies in Anki first."
        )
    if ids:
        _link(session, attempt, ids[0])
        return True
    return False


def _attachments(session, attempt, fields):
    from pathlib import Path

    snap = attempt.snapshot
    mapping = snap["profile"]["fields"]
    warnings = []
    if not snap.get("include_media"):
        return warnings
    path = Path(snap["path"]) if snap.get("path") else None
    stem = f"{attempt.export_key}-{digest(snap)[:12]}"
    if path and path.is_file() and snap["t1"] > snap["t0"]:
        if "SentenceAudio" in mapping:
            fields[mapping["SentenceAudio"]] = media._store(
                stem + "-sentence.mp3", media._clip(path, snap["t0"], snap["t1"])
            )
        if "Image" in mapping and snap.get("kind") == "video":
            name = stem + "-frame.jpg"
            ac(
                "storeMediaFile",
                filename=name,
                data=base64.b64encode(media._frame(path, (snap["t0"] + snap["t1"]) // 2)).decode(),
            )
            fields[mapping["Image"]] = f'<img src="{name}">'
    elif "SentenceAudio" in mapping:
        warnings.append(
            "Source audio unavailable; this note has text only. No substitute pronunciation was inferred."
        )
    if snap["profile"].get("word_tts") and "Audio" in mapping:
        # Never synthesize over a selected/local reading. Text-only is safer.
        item = session.get(SavedItem, attempt.saved_item_id) if attempt.saved_item_id else None
        sentence, _ = media._context(session, item) if item else (None, None)
        corrected = (
            any(
                word.get("reading_source") == "user"
                for word in (sentence.analysis or {}).get("words", [])
            )
            if sentence
            else False
        )
        if item and item.kind == "word" and not item.selected_reading and not corrected:
            try:
                fields[mapping["Audio"]] = media._store(
                    stem + "-word.mp3", media._tts(snap["fields"]["Simplified"])
                )
                warnings.append("Word audio is synthetic online TTS, not the source speaker.")
            except Exception:
                warnings.append("Optional online word TTS failed; no word audio was attached.")
    return warnings


def run_attempts(session, ids, progress=lambda message: None):
    checks = {}
    for n, attempt_id in enumerate(ids):
        attempt = session.get(ExportAttempt, attempt_id)
        if not attempt or attempt.status in {"added", "already_exported", "removed"}:
            continue
        progress(f"Exporting {n + 1}/{len(ids)}")
        uncertain = attempt.status == "uncertain" or not attempt.snapshot.get("allow_add", True)
        try:
            if reconcile(session, attempt):
                continue
            if uncertain:
                attempt.status = "uncertain"
                attempt.error = (
                    "No tagged note was found. Check Anki before explicitly allowing another add."
                )
                session.commit()
                continue
            item = session.get(SavedItem, attempt.saved_item_id) if attempt.saved_item_id else None
            if not item:
                attempt.status = "removed"
                attempt.error = "The saved card was removed before export"
                session.commit()
                continue
            if item.archived:
                raise HandoffConflict(
                    "The saved card is suspended. Resume it and refresh the preview."
                )
            link = session.scalar(select(AnkiLink).where(AnkiLink.saved_item_id == item.id))
            if link:
                attempt.status = "already_exported"
                attempt.note_id = link.note_id
                session.commit()
                continue
            from .profile import Profile

            profile = Profile.model_validate(attempt.snapshot["profile"])
            profile_key = digest(profile.model_dump())
            if profile_key not in checks:
                checks[profile_key] = preflight(profile)
            check = checks[profile_key]
            if not check["ok"]:
                raise HandoffConflict(
                    "Anki note type/deck/mapping no longer passes preflight. Open Settings."
                )
            session.refresh(item)
            if source(session, item, profile)[2] != attempt.snapshot["source_hash"]:
                raise HandoffConflict(
                    "Source text/reading/timing changed after preview. Refresh and export again."
                )
            import html

            fields = {
                target: html.escape(attempt.snapshot["fields"].get(key, "")).replace("\n", "<br>")
                for key, target in profile.fields.items()
            }
            if not fields.get(check["model_fields"][0], "").strip():
                raise HandoffConflict("The first Anki field is blank")
            if not attempt.snapshot.get("allow_duplicate"):
                import json

                similar = ac(
                    "findNotes",
                    query=json.dumps(
                        f"{profile.fields[chinese_key(profile)]}:{attempt.snapshot['fields'][chinese_key(profile)]}",
                        ensure_ascii=False,
                    ),
                )
                if similar:
                    raise HandoffConflict(
                        "A note with this Chinese text already exists. Re-preview and explicitly allow another note if intended."
                    )
            attempt.warnings = _attachments(session, attempt, fields)
            session.refresh(item)
            if (
                item.archived
                or source(session, item, profile)[2] != attempt.snapshot["source_hash"]
            ):
                raise HandoffConflict(
                    "Source or suspension changed during media preparation. Refresh the preview."
                )
            # Persist uncertainty BEFORE the external mutation. A worker crash or
            # failed local commit can then reconcile its exact remote marker.
            attempt.status = "uncertain"
            attempt.error = "Waiting for Anki confirmation"
            session.commit()
            try:
                note_id = ac(
                    "addNote",
                    note={
                        "deckName": profile.deck,
                        "modelName": profile.model,
                        "fields": fields,
                        "tags": [media.TAG, attempt.export_key],
                        "options": {
                            "allowDuplicate": bool(attempt.snapshot.get("allow_duplicate")),
                            "duplicateScope": "collection",
                        },
                    },
                )
                _link(session, attempt, note_id)
            except AnkiUnavailable:
                attempt.error = "Anki did not confirm whether the note was added. Check for its export tag before retrying."
                session.commit()
            except AnkiError as error:
                attempt.status = "error"
                attempt.error = str(error)[:500]
                session.commit()
        except Exception as error:
            session.rollback()
            attempt = session.get(ExportAttempt, attempt_id)
            # Once addNote might have run, retain uncertainty even on DB errors.
            if attempt.status != "uncertain":
                attempt.status = "error"
            attempt.error = (
                str(error)[:500]
                if isinstance(error, (HandoffConflict, AnkiError))
                else "Export interrupted. Check the Anki tag before retrying; the submitted snapshot is retained."
            )
            attempt.updated_at = datetime.now(timezone.utc)
            session.commit()
    rows = session.scalars(select(ExportAttempt).where(ExportAttempt.id.in_(ids))).all()
    summary = {
        "added": sum(row.status == "added" for row in rows),
        "skipped": sum(row.status != "added" for row in rows),
        "results": [
            {"saved_item_id": row.original_saved_item_id, "status": row.status, "error": row.error}
            for row in rows
        ],
    }
    session.merge(
        Setting(
            key="anki_last_export", value={"at": datetime.now(timezone.utc).isoformat(), **summary}
        )
    )
    session.commit()
    return {
        "added": summary["added"],
        "skipped": summary["skipped"],
        "details": "See persistent export inbox",
    }
