"""Export mined items to Anki. Reuses the "Xiehanzi Mandarin" note type
(templates/styling already render it) into a Mined::Immersion deck.

Two halves: build_preview is fast and side-effect-free (field building + dup
detection across the whole collection) and runs in the API process; export
committed items runs as a worker job because media generation (ffmpeg cue
clips, frame grabs, edge-tts word audio) takes seconds per item."""

from __future__ import annotations

import asyncio
import base64
import hashlib
import json
import subprocess
import tempfile
from datetime import datetime, timezone
from pathlib import Path

from pypinyin import Style, pinyin as py
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..config import settings
from ..models import AnkiLink, Lexeme, MediaItem, MediaRoot, SavedItem, Sentence, Setting
from ..timing import effective_times
from .connect import AnkiError, ac

NOTE_TYPE = "Xiehanzi Mandarin"
DECK = "Mined::Immersion"
TAG = "immersion-app"
CLIP_PRE_MS = 250
CLIP_POST_MS = 350
IMAGE_FIELDS = ("Image", "Picture", "Screenshot")  # first that exists on the note type


def _marks(text: str) -> str:
    return " ".join(s[0] for s in py(text, style=Style.TONE) if s[0].strip())


def _note_id(simplified: str) -> str:
    """Deck convention for the ID field (first field): word + toneless pinyin,
    e.g. 的 -> '的de'. Keeps Anki's first-field dup check word-keyed."""
    toneless = "".join(s[0] for s in py(simplified, style=Style.NORMAL))
    return f"{simplified}{toneless}"


def _context(session: Session, item: SavedItem) -> tuple[Sentence | None, dict | None]:
    """Preferred sentence context: a live row when it survived re-ingestion,
    else the snapshot (text only — no media without timings/item)."""
    for ctx in sorted(item.contexts, key=lambda c: c.added_at, reverse=True):
        if ctx.sentence_id:
            s = session.get(Sentence, ctx.sentence_id)
            if s is not None:
                return s, ctx.snapshot
    snap = next((c.snapshot for c in item.contexts if c.snapshot), None)
    return None, snap


def _fields(session: Session, item: SavedItem) -> tuple[dict, dict]:
    """(fields, meta). Meaning comes from CEDICT and is editable in the tray."""
    sentence, snap = _context(session, item)
    zh = sentence.zh if sentence else (snap or {}).get("zh", "")
    en = (sentence.en if sentence else (snap or {}).get("en")) or ""

    if item.kind == "word" and item.lexeme_id:
        lex = session.get(Lexeme, item.lexeme_id)
        simplified = lex.simplified
        traditional = lex.traditional or ""
        from pypinyin.contrib.tone_convert import to_tone
        context_words = ((sentence.analysis if sentence else (snap or {}).get("analysis")) or {}).get("words", [])
        occurrence_start = (snap or {}).get("occurrence_start")
        contextual_reading = next((w.get("reading") for w in context_words
                                   if w.get("lex") == item.lexeme_id and w.get("reading")
                                   and (occurrence_start is None or w.get("start") == occurrence_start)), None)
        reading = item.selected_reading or contextual_reading
        pinyin = (" ".join(to_tone(s) for s in reading.split()) if reading else _marks(simplified))
        from ..lingua.cedict import load as load_cedict

        gl = load_cedict().gloss(simplified) or []
        meaning = item.selected_meaning or "; ".join(d for g in gl for d in g.get("defs", []))[:500]
    else:
        simplified = item.surface or zh
        traditional = ""
        pinyin = _marks(simplified)
        meaning = en

    words = ((sentence.analysis if sentence else (snap or {}).get("analysis")) or {}).get("words", [])
    sentence_pinyin = " ".join(" ".join(w.get("py", [w["t"]])) for w in words) if words else _marks(zh)
    if item.selected_reading and words:
        from pypinyin.contrib.tone_convert import to_tone
        start = (snap or {}).get("occurrence_start")
        sentence_pinyin = " ".join(
            " ".join(to_tone(s) for s in item.selected_reading.split())
            if w.get("lex") == item.lexeme_id and (start is None or w.get("start") == start)
            else " ".join(w.get("py", [w["t"]])) for w in words)
    media_item = session.get(MediaItem, sentence.item_id) if sentence else None
    t0, t1 = effective_times(session, sentence) if sentence else (0, 0)
    return (
        {
            "ID": (_note_id(simplified) + ("-s" + hashlib.sha256(f"{item.selected_reading}:{item.selected_meaning}".encode()).hexdigest()[:10] if item.selected_reading or item.selected_meaning else "")),
            "Simplified": simplified,
            "Traditional": traditional,
            "Pinyin": pinyin,
            "Meaning": meaning,
            "Sentence": zh,
            "SentenceTraditional": (sentence.trad if sentence else None) or "",
            "SentencePinyin": sentence_pinyin,
            "SentenceMeaning": en,
        },
        {
            "sentence_id": sentence.id if sentence else None,
            "can_clip": bool(sentence and media_item and media_item.available and t1 > t0),
            "can_image": bool(media_item and media_item.kind == "video" and media_item.available),
        },
    )


def build_preview(session: Session, saved_item_ids: list[int]) -> dict:
    items = session.scalars(select(SavedItem).where(SavedItem.id.in_(saved_item_ids))).all()
    links = {
        link.saved_item_id: link
        for link in session.scalars(
            select(AnkiLink).where(AnkiLink.saved_item_id.in_(saved_item_ids))
        )
    }
    out = []
    for item in items:
        fields, meta = _fields(session, item)
        dup_ids = ac("findNotes", query=f'"Simplified:{fields["Simplified"]}"') if fields["Simplified"] else []
        dup_meanings = []
        if dup_ids:
            import re

            for info in ac("notesInfo", notes=dup_ids[:3]):
                raw = (info.get("fields", {}).get("Meaning") or {}).get("value", "")
                dup_meanings.append(re.sub(r"<[^>]+>", "", raw).strip()[:80])
        link = links.get(item.id)
        out.append({
            "saved_item_id": item.id,
            "kind": item.kind,
            "fields": fields,
            **meta,
            "duplicates": len(dup_ids),
            "duplicate_meanings": dup_meanings,
            "already_exported": link.note_id if link else None,
        })
    return {"deck": DECK, "model": NOTE_TYPE, "items": out}


# ---- media builders (worker only) -------------------------------------------


def _media_source(session: Session, sentence: Sentence) -> Path | None:
    item = session.get(MediaItem, sentence.item_id)
    if item is None or not item.available:
        return None
    if item.kind == "audio":  # prefer the seek-accurate m4a cache
        m4a = settings.audio_dir / f"{item.id}.m4a"
        if m4a.exists():
            return m4a
    root = session.get(MediaRoot, item.root_id)
    return Path(root.path) / item.relpath


def _clip(src: Path, t0_ms: int, t1_ms: int) -> bytes:
    t0 = max(0, t0_ms - CLIP_PRE_MS) / 1000
    t1 = (t1_ms + CLIP_POST_MS) / 1000
    with tempfile.NamedTemporaryFile(suffix=".mp3") as f:
        subprocess.run(
            ["ffmpeg", "-loglevel", "error", "-ss", f"{t0:.3f}", "-to", f"{t1:.3f}",
             "-i", str(src), "-vn", "-c:a", "libmp3lame", "-b:a", "96k", "-y", f.name],
            check=True,
        )
        return Path(f.name).read_bytes()


def _frame(src: Path, t_ms: int) -> bytes:
    with tempfile.NamedTemporaryFile(suffix=".jpg") as f:
        subprocess.run(
            ["ffmpeg", "-loglevel", "error", "-ss", f"{t_ms / 1000:.3f}", "-i", str(src),
             "-frames:v", "1", "-vf", "scale=640:-2", "-y", f.name],
            check=True,
        )
        return Path(f.name).read_bytes()


def _tts(word: str) -> bytes:
    import edge_tts

    async def run() -> bytes:
        chunks = []
        async for chunk in edge_tts.Communicate(word, settings.tts_voice).stream():
            if chunk["type"] == "audio":
                chunks.append(chunk["data"])
        return b"".join(chunks)

    return asyncio.run(run())


def _store(filename: str, data: bytes) -> str:
    ac("storeMediaFile", filename=filename, data=base64.b64encode(data).decode())
    return f"[sound:{filename}]"


def export_items(session: Session, entries: list[dict], progress=lambda msg: None) -> dict:
    """entries: [{saved_item_id, fields, allow_duplicate, include_media}]. The
    tray sends final (possibly edited) fields; media is generated here."""
    ac("createDeck", deck=DECK)
    model_fields = set(ac("modelFieldNames", modelName=NOTE_TYPE))
    image_field = next((f for f in IMAGE_FIELDS if f in model_fields), None)

    results = []
    for n, entry in enumerate(entries):
        item = session.get(SavedItem, entry["saved_item_id"])
        if item is None:
            results.append({"saved_item_id": entry["saved_item_id"], "status": "missing"})
            continue
        if session.scalar(select(AnkiLink).where(AnkiLink.saved_item_id == item.id)):
            results.append({"saved_item_id": item.id, "status": "already_exported"})
            continue
        progress(f"exporting {n + 1}/{len(entries)}: {entry['fields'].get('Simplified', '')}")

        fields = {k: v for k, v in entry["fields"].items() if k in model_fields}
        if entry.get("allow_duplicate") and "ID" in model_fields and fields.get("ID"):
            fields["ID"] += f"-m{item.id}"  # distinct first field so Anki accepts it
        sentence, _snap = _context(session, item)
        if entry.get("include_media", True) and sentence is not None:
            src = _media_source(session, sentence)
            stem = f"immersion-{item.id}"
            t0, t1 = effective_times(session, sentence)
            if src is not None and t1 > t0:
                if "SentenceAudio" in model_fields:
                    fields["SentenceAudio"] = _store(f"{stem}-sentence.mp3", _clip(src, t0, t1))
                media_item = session.get(MediaItem, sentence.item_id)
                if image_field and media_item and media_item.kind == "video":
                    mid = (t0 + t1) // 2
                    data = _frame(src, mid)
                    ac("storeMediaFile", filename=f"{stem}-frame.jpg", data=base64.b64encode(data).decode())
                    fields[image_field] = f'<img src="{stem}-frame.jpg">'
            if item.kind == "word" and not item.selected_reading and "Audio" in model_fields:
                try:
                    fields["Audio"] = _store(f"{stem}-word.mp3", _tts(fields.get("Simplified", "")))
                except Exception:
                    pass  # TTS is online; a miss shouldn't sink the note

        try:
            note_id = ac("addNote", note={
                "deckName": DECK, "modelName": NOTE_TYPE, "fields": fields, "tags": [TAG],
                "options": {"allowDuplicate": bool(entry.get("allow_duplicate")),
                            "duplicateScope": "collection"},
            })
        except AnkiError as e:
            results.append({"saved_item_id": item.id, "status": "error", "error": str(e)[:200]})
            continue

        session.add(AnkiLink(
            lexeme_id=item.lexeme_id, saved_item_id=item.id, note_id=note_id,
            deck=DECK, model=NOTE_TYPE,
            fields_hash=hashlib.sha256(json.dumps(fields, sort_keys=True).encode()).hexdigest()[:16],
        ))
        session.commit()  # per-note checkpoint: a later failure keeps earlier links
        results.append({"saved_item_id": item.id, "status": "added", "note_id": note_id})

    summary = {
        "added": sum(1 for r in results if r["status"] == "added"),
        "skipped": sum(1 for r in results if r["status"] != "added"),
        "at": datetime.now(timezone.utc).isoformat(),
        "results": results,
    }
    session.merge(Setting(key="anki_last_export", value=summary))
    session.commit()
    return summary
