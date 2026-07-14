"""Whisper zh-track generation for unsubbed video (HSK Courses, Integrated
Chinese, TV rips with no usable subtitles).

Unlike podcasts — where an official transcript is ground truth and whisper only
contributes timings — here whisper's own text becomes the zh track, segmented
into sentences by its punctuation plus gap/length limits. faster-whisper reads
the video container directly (PyAV demuxes the audio), so no extraction step.

Word timings are cached per fingerprint in the same whisper cache the podcast
path uses; a re-ingest after transcript edits never re-burns GPU minutes."""

from __future__ import annotations

import json

from sqlalchemy import select
from sqlalchemy.orm import Session

from ..config import settings
from ..jobs import enqueue
from ..lingua.pipeline import SENT_END
from ..models import MediaItem, MediaRoot, Series, TextTrack
from .subtitles import Segment

MAX_GAP_S = 1.2  # silence longer than this starts a new sentence
MAX_SPAN_S = 12.0
MAX_CHARS = 40


def _join(words: list[tuple[str, float, float]]) -> str:
    """Concatenate whisper tokens; keep a space only at latin-latin joins."""
    out = ""
    for w, _s, _e in words:
        if out and w and out[-1].isascii() and out[-1].isalnum() and w[0].isascii() and w[0].isalnum():
            out += " "
        out += w
    return out


def words_to_segments(words: list[tuple[str, float, float]]) -> list[Segment]:
    """Sentence segments from whisper words: break on sentence-final
    punctuation, long silence, or runaway length."""
    segs: list[Segment] = []
    buf: list[tuple[str, float, float]] = []

    def flush() -> None:
        if buf:
            text = _join(buf).strip()
            if text:
                segs.append(Segment(round(buf[0][1] * 1000), round(buf[-1][2] * 1000), text))
            buf.clear()

    for word, start, end in words:
        if not word:
            continue
        if buf:
            gap = start - buf[-1][2]
            span = end - buf[0][1]
            chars = sum(len(w) for w, _, _ in buf)
            if gap > MAX_GAP_S or span > MAX_SPAN_S or chars > MAX_CHARS:
                flush()
        buf.append((word, start, end))
        if word[-1] in SENT_END:
            flush()
    flush()
    return segs


def whisper_transcribe_item(session: Session, item_id: int, progress=lambda msg: None) -> dict:
    from ..lingua.align import transcribe_words
    from .align_tracks import assign_en
    from .analysis import make_thumb, resolve_track_path, write_sentences
    from .subtitles import parse_cues

    item = session.get(MediaItem, item_id)
    if item is None or not item.available or item.kind != "video":
        return {"skipped": True}
    root = session.get(MediaRoot, item.root_id)
    base = root.path
    from pathlib import Path

    video = Path(base) / item.relpath

    # a real subtitle track may have appeared since this was queued
    real_zh = session.scalar(
        select(TextTrack).where(
            TextTrack.item_id == item.id, TextTrack.lang == "zh",
            TextTrack.selected, TextTrack.source.in_(("sidecar", "embedded")),
        )
    )
    if real_zh is not None:
        return {"skipped": "subtitle zh track exists"}

    cache = settings.whisper_dir / f"{item.id}.json"
    words: list[tuple[str, float, float]] | None = None
    if cache.exists():
        data = json.loads(cache.read_text())
        if data.get("fp") == item.fingerprint:
            words = [tuple(w) for w in data["words"]]
    if words is None:
        progress("transcribing (whisper)")
        words = transcribe_words(str(video))
        settings.whisper_dir.mkdir(parents=True, exist_ok=True)
        cache.write_text(json.dumps({"fp": item.fingerprint, "words": words}))

    segments = words_to_segments(words)
    if not segments:
        return {"skipped": "no speech detected"}

    track = session.scalar(
        select(TextTrack).where(TextTrack.item_id == item.id, TextTrack.source == "whisper")
    )
    if track is None:
        track = TextTrack(
            item_id=item.id, lang="zh", source="whisper", relpath=None,
            format=None, meta={"engine": "faster-whisper"},
        )
        session.add(track)
        session.flush()
    track.content_hash = item.fingerprint  # regenerated per content revision

    en_assign = None
    en = session.scalar(
        select(TextTrack).where(
            TextTrack.item_id == item.id, TextTrack.lang == "en",
            TextTrack.selected, TextTrack.source.in_(("sidecar", "embedded")),
        )
    )
    if en is not None:
        en_path = resolve_track_path(base, item, en)
        if en_path is not None:
            en_cues, _ = parse_cues(en_path, "en")
            en_assign = assign_en(segments, en_cues)

    progress(f"analyzing {len(segments)} sentences")
    write_sentences(session, item, track, segments, en_assign)
    make_thumb(video, item.id, item.duration_ms)
    item.ready = True
    if item.series_id:
        series = session.get(Series, item.series_id)
        if series and series.cover_item_id is None:
            series.cover_item_id = item.id
    session.commit()
    enqueue(session, "translate_item", {"item_id": item.id})
    return {"sentences": len(segments)}
