"""Embedded subtitle extraction (MKV/MP4 text streams).

The scanner records each item's subtitle streams in meta['embedded_subs'] at
probe time; nothing is demuxed until ingest finds no sidecar for a language.
Extraction converts any text codec to SRT in the subs cache (keyed by item id
and stream index) — bitmap subs (PGS/VobSub) need OCR and are skipped.

Language: the stream's `language` tag decides when present; untagged streams
are extracted and content-sniffed (CJK ratio), the same rule bare sidecar .srt
files get."""

from __future__ import annotations

import hashlib
import subprocess
from pathlib import Path

from sqlalchemy import select
from sqlalchemy.orm import Session

from ..config import settings
from ..models import MediaItem, TextTrack
from .subtitles import cjk_ratio, sniff_read
from .video import EN_MARKERS, ZH_MARKERS

TEXT_SUB_CODECS = {"subrip", "srt", "ass", "ssa", "webvtt", "mov_text", "text"}


def sub_path(item_id: int, stream_index: int, fingerprint: str | None = None) -> Path:
    return settings.subs_dir / f"{item_id}.{stream_index}.{fingerprint or 'legacy'}.srt"


def extract_stream(video: Path, stream_index: int, out: Path) -> bool:
    """Demux one subtitle stream to SRT. False when ffmpeg can't convert it."""
    out.parent.mkdir(parents=True, exist_ok=True)
    temporary = out.with_suffix(".part.srt")
    try:
        proc = subprocess.run(
            ["ffmpeg", "-loglevel", "error", "-i", str(video),
             "-map", f"0:{stream_index}", "-c:s", "srt", "-y", str(temporary)],
            capture_output=True, text=True, timeout=120,
        )
    except subprocess.TimeoutExpired:
        temporary.unlink(missing_ok=True)
        return False
    if proc.returncode != 0 or not temporary.exists() or temporary.stat().st_size == 0:
        temporary.unlink(missing_ok=True)
        return False
    temporary.replace(out)
    return True


def _stream_lang(stream: dict) -> str | None:
    tag = (stream.get("lang") or "").lower()
    if tag in ZH_MARKERS:
        return "zh"
    if tag in EN_MARKERS:
        return "en"
    return None  # untagged or something else: sniff after extraction


def ensure_embedded_tracks(session: Session, item: MediaItem, video: Path) -> list[TextTrack]:
    """Extract text streams for languages that have no sidecar; upsert
    TextTrack(source='embedded') rows. Returns the item's embedded tracks.
    Records the attempt in meta['embedded_checked'] so unchanged items aren't
    re-demuxed every scan."""
    streams = (item.meta or {}).get("embedded_subs") or []
    existing = session.scalars(
        select(TextTrack).where(TextTrack.item_id == item.id, TextTrack.source == "embedded")
    ).all()
    by_index = {(t.meta or {}).get("stream_index"): t for t in existing}

    successful = set()
    for s in streams:
        idx = s.get("index")
        if idx is None or (s.get("codec") or "") not in TEXT_SUB_CODECS:
            continue
        lang = _stream_lang(s)
        out = sub_path(item.id, idx, item.fingerprint)
        if (not out.is_file() or out.stat().st_size == 0) and not extract_stream(video, idx, out):
            continue
        if lang is None:
            try:
                text, _enc = sniff_read(out)
            except (UnicodeDecodeError, OSError):
                continue
            lang = "zh" if cjk_ratio(text) > 0.2 else "en"
        successful.add(idx)
        content_hash = hashlib.sha256(out.read_bytes()).hexdigest()[:16]
        track = by_index.get(idx)
        if track is None:
            track = TextTrack(
                item_id=item.id, lang=lang, source="embedded", relpath=None,
                format="srt", encoding="utf-8", content_hash=content_hash,
                meta={"stream_index": idx, "codec": s.get("codec"), "available": True, "fingerprint": item.fingerprint},
            )
            session.add(track)
            existing.append(track)
        else:
            track.content_hash = content_hash
            track.lang = lang
            track.meta = {**(track.meta or {}), "available": True, "fingerprint": item.fingerprint}

    for track in existing:
        if (track.meta or {}).get("stream_index") not in successful:
            track.meta = {**(track.meta or {}), "available": False}
            track.selected = False
    item.meta = {**(item.meta or {}), "embedded_checked": item.fingerprint}
    session.flush()
    from ..tracks import choose_tracks
    choose_tracks(session, item)
    session.flush()
    return existing


def has_embedded_candidate(item: MediaItem) -> bool:
    """Cheap scan-time check: is there a text stream worth extracting?"""
    return any(
        (s.get("codec") or "") in TEXT_SUB_CODECS
        for s in (item.meta or {}).get("embedded_subs") or []
    )
