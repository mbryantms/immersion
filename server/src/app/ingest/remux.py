"""Remux/transcode non-direct-play video into browser-safe mp4.

Direct play is the common case (LFC is all h264 mp4) and never touches this
module. Anything else — mkv/other containers, hevc/mpeg4/etc. video, ac3/dts
audio — gets one cached mp4: stream-copy when the codec already plays in
browsers (mkv h264 → mp4 h264 is a cheap rewrap), libx264 otherwise. hevc is
transcoded too: Safari plays it but desktop Chrome usually can't, and one
universal file beats per-browser variants.

The cache is keyed by content fingerprint in item.meta['remux']; stream_url
switches to /media/remux/{id}.mp4 only when the recorded fp is current."""

from __future__ import annotations

import subprocess
from pathlib import Path

from sqlalchemy.orm import Session

from ..config import settings
from ..models import MediaItem, MediaRoot

DIRECT_EXTS = {".mp4", ".m4v", ".webm"}
DIRECT_VIDEO = {"h264", "vp8", "vp9", "av1"}
DIRECT_AUDIO = {"aac", "mp3", "opus", "vorbis", "flac"}


def needs_remux(item: MediaItem) -> bool:
    if item.kind != "video" or not item.available or item.vcodec is None:
        return False
    ext = Path(item.relpath).suffix.lower()
    if ext in (".mp4", ".m4v"):
        return item.vcodec not in {"h264", "av1"} or item.acodec not in {None, "aac", "mp3"}
    if ext == ".webm":
        return item.vcodec not in {"vp8", "vp9", "av1"} or item.acodec not in {None, "opus", "vorbis"}
    return True


def remux_current(item: MediaItem) -> bool:
    meta = (item.meta or {}).get("remux") or {}
    output = settings.remux_dir / f"{item.id}.mp4"
    return bool(meta and meta.get("fp") == item.fingerprint and output.is_file() and output.stat().st_size > 0)


def remux_item(session: Session, item_id: int, progress=lambda msg: None, force=False) -> dict:
    item = session.get(MediaItem, item_id)
    if item is None or not item.available or (not force and not needs_remux(item)):
        return {"skipped": True}
    out = settings.remux_dir / f"{item.id}.mp4"
    if not force and remux_current(item):
        return {"skipped": "remux current"}

    root = session.get(MediaRoot, item.root_id)
    src = Path(root.path) / item.relpath
    v_copy = not force and item.vcodec == "h264"
    a_copy = not force and item.acodec in {None, "aac", "mp3"}
    v_args = ["-c:v", "copy"] if v_copy else [
        "-c:v", "libx264", "-crf", "22", "-preset", "veryfast", "-pix_fmt", "yuv420p",
    ]
    a_args = ["-c:a", "copy"] if a_copy else ["-c:a", "aac", "-b:a", "160k"]
    progress("rewrapping (stream copy)" if v_copy else f"transcoding {item.vcodec} → h264")

    settings.remux_dir.mkdir(parents=True, exist_ok=True)
    tmp = out.with_suffix(".part.mp4")
    try:
        subprocess.run(
            ["ffmpeg", "-loglevel", "error", "-i", str(src),
             "-map", "0:v:0", "-map", "0:a:0?", "-sn", "-dn",
             *v_args, *a_args, "-movflags", "+faststart", "-y", str(tmp)],
            check=True, capture_output=True, text=True, timeout=7200,
        )
    except (subprocess.CalledProcessError, subprocess.TimeoutExpired) as e:
        tmp.unlink(missing_ok=True)
        raise RuntimeError(f"ffmpeg remux failed: {(str(e.stderr or ''))[-500:]}") from e
    tmp.replace(out)

    from uuid import uuid4
    item.meta = {**(item.meta or {}), "remux": {
        "revision": uuid4().hex,
        "fp": item.fingerprint,
        "video": "copy" if v_copy else "h264",
        "audio": "copy" if a_copy else "aac",
    }}
    session.commit()
    return {"remuxed": item.id, "video": "copy" if v_copy else "h264"}
