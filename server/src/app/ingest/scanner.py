"""Library root scanning: walk, fingerprint, upsert items/tracks, queue ingest.

The filesystem is authoritative for media; the DB is an index. Missing files
are marked unavailable, never deleted — learning history must survive moves."""

from __future__ import annotations

import fnmatch
import hashlib
from pathlib import Path

import xxhash
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..jobs import enqueue
from ..models import MediaItem, MediaRoot, Series, TextTrack
from .subtitles import cjk_ratio, sniff_read
from .video import VIDEO_EXTS, episode_position, find_sidecars, infer_series, probe_summary


def fingerprint(path: Path) -> str:
    """xxhash of first+last 1MB + size; cheap but content-sensitive."""
    h = xxhash.xxh64()
    size = path.stat().st_size
    with open(path, "rb") as f:
        h.update(f.read(1 << 20))
        if size > 2 << 20:
            f.seek(-1 << 20, 2)
            h.update(f.read())
    h.update(str(size).encode())
    return h.hexdigest()


def _included(relpath: str, include_glob: str | None) -> bool:
    if not include_glob:
        return True
    return any(fnmatch.fnmatch(relpath, pat.strip()) for pat in include_glob.split(";"))


def scan_video_root(session: Session, root: MediaRoot, progress=lambda msg: None) -> dict:
    base = Path(root.path)
    seen_relpaths: set[str] = set()
    stats = {"new": 0, "changed": 0, "unchanged": 0, "missing": 0}
    existing = {
        i.relpath: i
        for i in session.scalars(select(MediaItem).where(MediaItem.root_id == root.id))
    }
    series_cache: dict[str, Series] = {}
    to_ingest: list[int] = []

    files = sorted(
        p for p in base.rglob("*")
        if p.suffix.lower() in VIDEO_EXTS and p.is_file()
        and _included(str(p.relative_to(base)), root.include_glob)
    )
    for n, path in enumerate(files):
        relpath = str(path.relative_to(base))
        seen_relpaths.add(relpath)
        st = path.stat()
        fast = f"{st.st_size}:{st.st_mtime_ns}"
        item = existing.get(relpath)
        if item and (item.meta or {}).get("fast_fp") == fast and item.available:
            stats["unchanged"] += 1
            # sidecar subs can change without the video changing
            if _sync_tracks(session, root, item, path):
                _queue_ingest(session, to_ingest, item.id)
            continue

        progress(f"probing {n + 1}/{len(files)}: {relpath}")
        fp = fingerprint(path)
        if item is None:
            title = path.stem
            series_title, level, ordinal = infer_series(relpath)
            # on-disk episode-dir order beats number-in-stem inference
            pos = episode_position(base, relpath)
            if pos is not None:
                ordinal = pos
            series = None
            if series_title:
                series = series_cache.get(series_title) or session.scalar(
                    select(Series).where(Series.root_id == root.id, Series.title == series_title)
                )
                if series is None:
                    series = Series(root_id=root.id, title=series_title, level_hint=level)
                    session.add(series)
                    session.flush()
                series_cache[series_title] = series
            item = MediaItem(
                root_id=root.id, series_id=series.id if series else None,
                relpath=relpath, title=title, ordinal=ordinal, kind="video",
            )
            session.add(item)
            stats["new"] += 1
        elif item.fingerprint != fp or not item.available:
            stats["changed"] += 1
        else:
            stats["unchanged"] += 1
            item.meta = {**(item.meta or {}), "fast_fp": fast}
            if _sync_tracks(session, root, item, path):
                _queue_ingest(session, to_ingest, item.id)
            continue

        probe = probe_summary(path)
        item.fingerprint = fp
        item.available = True
        item.duration_ms = probe["duration_ms"]
        item.vcodec, item.acodec = probe["vcodec"], probe["acodec"]
        item.width, item.height = probe["width"], probe["height"]
        item.meta = {**(item.meta or {}), "fast_fp": fast, "embedded_subs": probe["embedded_subs"]}
        session.flush()
        _sync_tracks(session, root, item, path)
        _queue_ingest(session, to_ingest, item.id)
        if n % 20 == 0:
            session.commit()

    for relpath, item in existing.items():
        if relpath not in seen_relpaths and item.available:
            item.available = False
            stats["missing"] += 1
    session.commit()
    return {"stats": stats, "ingest_item_ids": sorted(set(to_ingest))}


def _queue_ingest(session: Session, to_ingest: list[int], item_id: int) -> None:
    """Enqueue as we go, not after the walk: an interrupted scan must not lose
    ingest work for items it already committed — the re-scan fast-paths them
    and would otherwise never ingest them (the Bird-and-Kip bug)."""
    to_ingest.append(item_id)
    enqueue(session, "ingest_item", {"item_id": item_id})


def _sync_tracks(session: Session, root: MediaRoot, item: MediaItem, path: Path) -> bool:
    """Upsert sidecar tracks; True when a selected track is new or its content
    changed (i.e. the item needs (re-)ingestion)."""
    base = Path(root.path)
    changed = False
    existing = {
        t.relpath: t
        for t in session.scalars(
            select(TextTrack).where(TextTrack.item_id == item.id, TextTrack.source == "sidecar")
        )
    }
    for side in find_sidecars(path):
        f: Path = side["path"]
        rel = str(f.relative_to(base))
        try:
            text, encoding = sniff_read(f)
        except (UnicodeDecodeError, OSError):
            continue
        lang = side["lang"] or ("zh" if cjk_ratio(text) > 0.2 else "en")
        content_hash = hashlib.sha256(text.encode()).hexdigest()[:16]
        track = existing.get(rel)
        if track is None:
            session.add(TextTrack(
                item_id=item.id, lang=lang, source="sidecar", relpath=rel,
                format=f.suffix.lstrip(".").lower(), encoding=encoding,
                content_hash=content_hash,
            ))
            changed = True
        elif track.content_hash != content_hash:
            track.content_hash = content_hash
            track.encoding = encoding
            changed = True
    if changed:
        session.flush()
    return changed
