"""Podcast root scanning + ingest. Ported from podreader's cmd_scan.

Layout convention: each immediate subdirectory of the root is one show;
episodes pair `*-transcript.txt` (or .srt) with an audio file by the first
integer in each filename. Audio is transcoded once to m4a AAC in the cache —
podcast VBR MP3s lack seek tables, so browser currentTime seeks land seconds
off; AAC seeks sample-accurately.

Pipeline per episode (three jobs, each checkpointed by the previous one's
committed output): ingest_item (transcode + analyze, times zeroed) ->
whisper_align (GPU timing, sets ready) -> translate_item (claude CLI)."""

from __future__ import annotations

import hashlib
import json
import re
import subprocess
import time
from pathlib import Path

from sqlalchemy import select
from sqlalchemy.orm import Session

from ..config import settings
from ..jobs import enqueue
from ..lingua.pipeline import split_sentences
from ..models import MediaItem, MediaRoot, Sentence, Series, TextTrack
from .analysis import write_sentences
from .scanner import _included, fingerprint
from .subtitles import Segment, sniff_read
from .video import probe_summary

AUDIO_EXTS = {".mp3", ".m4a", ".m4b", ".flac", ".ogg", ".opus", ".wav"}
TRANSCRIPT_EXTS = {".txt", ".srt"}
COVER_NAMES = ("cover.jpg", "cover.png", "folder.jpg", "folder.png")
MTIME_GUARD_S = 60  # files saved <1min ago are probably still being written


def first_int(name: str) -> int | None:
    m = re.search(r"\d+", name)
    return int(m.group()) if m else None


def find_cover(showdir: Path) -> Path | None:
    return next((showdir / n for n in COVER_NAMES if (showdir / n).exists()), None)


def read_transcript(path: Path) -> str:
    """Transcript text; .srt input has cue numbers and timecode lines stripped."""
    text, _enc = sniff_read(path)
    if path.suffix.lower() != ".srt":
        return text
    lines = [
        ln for ln in text.splitlines()
        if ln.strip() and "-->" not in ln and not ln.strip().isdigit()
    ]
    return "".join(lines)


def scan_podcast_root(session: Session, root: MediaRoot, progress=lambda msg: None) -> dict:
    base = Path(root.path)
    stats = {"new": 0, "changed": 0, "unchanged": 0, "missing": 0, "skipped": 0}
    existing = {
        i.relpath: i
        for i in session.scalars(select(MediaItem).where(MediaItem.root_id == root.id))
    }
    seen_relpaths: set[str] = set()
    to_ingest: list[int] = []

    for showdir in sorted(p for p in base.iterdir() if p.is_dir()):
        audios = sorted(p for p in showdir.iterdir() if p.suffix.lower() in AUDIO_EXTS)
        transcripts = sorted(p for p in showdir.iterdir() if p.suffix.lower() in TRANSCRIPT_EXTS)
        if not audios or not transcripts:
            continue
        series = session.scalar(
            select(Series).where(Series.root_id == root.id, Series.title == showdir.name)
        )
        if series is None:
            series = Series(root_id=root.id, title=showdir.name)
            session.add(series)
            session.flush()
        cover = find_cover(showdir)

        for t in transcripts:
            if time.time() - t.stat().st_mtime < MTIME_GUARD_S:
                stats["skipped"] += 1  # probably still saving — next scan
                continue
            n = first_int(t.name)
            if n is not None:
                matches = [a for a in audios if first_int(a.name) == n]
            else:
                matches = audios if len(audios) == 1 else []
            if len(matches) != 1:
                stats["skipped"] += 1
                continue
            audio = matches[0]
            relpath = str(audio.relative_to(base))
            if not _included(relpath, root.include_glob):
                continue
            seen_relpaths.add(relpath)
            ordinal = n if n is not None else first_int(audio.name) or 0

            st = audio.stat()
            fast = f"{st.st_size}:{st.st_mtime_ns}"
            t_text, t_enc = sniff_read(t)
            t_hash = hashlib.sha256(t_text.encode()).hexdigest()[:16]

            item = existing.get(relpath)
            if item is None:
                progress(f"probing {showdir.name}/{audio.name}")
                item = MediaItem(
                    root_id=root.id, series_id=series.id, relpath=relpath,
                    title=audio.stem, ordinal=ordinal, kind="audio",
                )
                session.add(item)
                session.flush()
                stats["new"] += 1
            elif (item.meta or {}).get("fast_fp") == fast and item.available:
                if _sync_transcript(session, item, t, base, t_hash, t_enc):
                    stats["changed"] += 1
                    to_ingest.append(item.id)
                    enqueue(session, "ingest_item", {"item_id": item.id})
                else:
                    stats["unchanged"] += 1
                continue
            else:
                progress(f"probing {showdir.name}/{audio.name}")
                stats["changed"] += 1

            probe = probe_summary(audio)
            item.fingerprint = fingerprint(audio)
            item.available = True
            item.duration_ms = probe["duration_ms"]
            item.acodec = probe["acodec"]
            item.meta = {
                **(item.meta or {}),
                "fast_fp": fast,
                "cover": str(cover.relative_to(base)) if cover else None,
            }
            session.flush()
            _sync_transcript(session, item, t, base, t_hash, t_enc)
            to_ingest.append(item.id)
            enqueue(session, "ingest_item", {"item_id": item.id})  # crash-safe: as we go

    for relpath, item in existing.items():
        if item.kind == "audio" and relpath not in seen_relpaths and item.available:
            item.available = False
            stats["missing"] += 1
    session.commit()
    return {"stats": stats, "ingest_item_ids": sorted(set(to_ingest))}


def _sync_transcript(
    session: Session, item: MediaItem, path: Path, base: Path, content_hash: str, encoding: str
) -> bool:
    """Upsert the transcript track; True when new or content changed."""
    rel = str(path.relative_to(base))
    track = session.scalar(
        select(TextTrack).where(TextTrack.item_id == item.id, TextTrack.source == "transcript")
    )
    if track is None:
        session.add(TextTrack(
            item_id=item.id, lang="zh", source="transcript", relpath=rel,
            format=path.suffix.lstrip(".").lower(), encoding=encoding,
            content_hash=content_hash,
        ))
        session.flush()
        return True
    if track.relpath != rel or track.content_hash != content_hash:
        track.relpath = rel
        track.content_hash = content_hash
        track.encoding = encoding
        session.flush()
        return True
    return False


def transcode_m4a(audio_path: Path, item: MediaItem) -> Path:
    """Transcode into the audio cache once per content fingerprint."""
    settings.audio_dir.mkdir(parents=True, exist_ok=True)
    out = settings.audio_dir / f"{item.id}.m4a"
    if out.exists() and (item.meta or {}).get("m4a_fp") == item.fingerprint:
        return out
    subprocess.run(
        ["ffmpeg", "-loglevel", "error", "-i", str(audio_path),
         "-vn", "-c:a", "aac", "-b:a", "128k", "-y", str(out)],
        check=True,
    )
    item.meta = {**(item.meta or {}), "m4a_fp": item.fingerprint}
    return out


def make_cover_thumb(cover_path: Path | None, item_id: int) -> None:
    if cover_path is None or not cover_path.exists():
        return
    settings.thumb_dir.mkdir(parents=True, exist_ok=True)
    out = settings.thumb_dir / f"{item_id}.jpg"
    if out.exists():
        return
    subprocess.run(
        ["ffmpeg", "-loglevel", "error", "-i", str(cover_path),
         "-vf", "scale=480:480:force_original_aspect_ratio=increase,crop=480:480",
         "-frames:v", "1", "-y", str(out)],
        check=False,
    )


def ingest_podcast_item(session: Session, item_id: int, progress=lambda msg: None) -> None:
    """Transcode + analyze one episode. Sentence times are zeroed until the
    whisper_align job (queued here) fills them and flips `ready`."""
    item = session.get(MediaItem, item_id)
    if item is None or not item.available or item.kind != "audio":
        return
    root = session.get(MediaRoot, item.root_id)
    base = Path(root.path)

    track = session.scalar(
        select(TextTrack).where(
            TextTrack.item_id == item.id, TextTrack.source == "transcript", TextTrack.selected
        )
    )
    if track is None or track.relpath is None:
        progress("no transcript; skipping")
        return

    progress("transcoding to m4a")
    transcode_m4a(base / item.relpath, item)

    progress("analyzing transcript")
    sentences = split_sentences(read_transcript(base / track.relpath))
    segments = [Segment(t0_ms=0, t1_ms=0, text=s) for s in sentences]
    write_sentences(session, item, track, segments, None)

    cover_rel = (item.meta or {}).get("cover")
    make_cover_thumb(base / cover_rel if cover_rel else None, item.id)
    if item.series_id:
        series = session.get(Series, item.series_id)
        if series and series.cover_item_id is None:
            series.cover_item_id = item.id
    item.ready = False  # playable once whisper_align sets times
    session.commit()
    enqueue(session, "whisper_align", {"item_id": item.id})


def whisper_align_item(session: Session, item_id: int, progress=lambda msg: None) -> dict:
    """Fill sentence [t0, t1] from whisper word timings; then queue translation.

    Word timings are cached per audio fingerprint so transcript edits re-align
    without re-transcribing (~GPU-minutes per episode)."""
    from ..lingua.align import sentence_times, transcribe_words

    item = session.get(MediaItem, item_id)
    if item is None or not item.available:
        return {"skipped": True}
    m4a = settings.audio_dir / f"{item.id}.m4a"
    if not m4a.exists():
        raise RuntimeError(f"m4a cache missing for item {item.id}; re-run ingest_item")

    cache = settings.whisper_dir / f"{item.id}.json"
    words: list[tuple[str, float, float]] | None = None
    if cache.exists():
        data = json.loads(cache.read_text())
        if data.get("fp") == item.fingerprint:
            words = [tuple(w) for w in data["words"]]
    if words is None:
        progress("transcribing (whisper)")
        words = transcribe_words(str(m4a))
        settings.whisper_dir.mkdir(parents=True, exist_ok=True)
        cache.write_text(json.dumps({"fp": item.fingerprint, "words": words}))

    sentences = session.scalars(
        select(Sentence).where(Sentence.item_id == item.id).order_by(Sentence.ordinal)
    ).all()
    if not sentences:
        return {"skipped": "no sentences"}
    progress(f"aligning {len(sentences)} sentences")
    times = sentence_times([s.zh for s in sentences], words)
    for s, (t0, t1) in zip(sentences, times):
        s.t0_ms = round(t0 * 1000)
        s.t1_ms = round(t1 * 1000)
    item.ready = True
    session.commit()
    enqueue(session, "translate_item", {"item_id": item.id})
    return {"aligned": len(sentences)}
