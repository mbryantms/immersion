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
    return (
        ext not in DIRECT_EXTS
        or item.vcodec not in DIRECT_VIDEO
        or (item.acodec is not None and item.acodec not in DIRECT_AUDIO)
    )


def remux_current(item: MediaItem) -> bool:
    return ((item.meta or {}).get("remux") or {}).get("fp") == item.fingerprint


def remux_item(session: Session, item_id: int, progress=lambda msg: None) -> dict:
    item = session.get(MediaItem, item_id)
    if item is None or not needs_remux(item):
        return {"skipped": True}
    out = settings.remux_dir / f"{item.id}.mp4"
    if remux_current(item) and out.exists():
        return {"skipped": "remux current"}

    root = session.get(MediaRoot, item.root_id)
    src = Path(root.path) / item.relpath
    v_copy = item.vcodec in DIRECT_VIDEO
    a_copy = item.acodec in DIRECT_AUDIO or item.acodec is None
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
            check=True, capture_output=True, text=True,
        )
    except subprocess.CalledProcessError as e:
        tmp.unlink(missing_ok=True)
        raise RuntimeError(f"ffmpeg remux failed: {(e.stderr or '')[-500:]}") from e
    tmp.replace(out)

    item.meta = {**(item.meta or {}), "remux": {
        "fp": item.fingerprint,
        "video": "copy" if v_copy else "h264",
        "audio": "copy" if a_copy else "aac",
    }}
    session.commit()
    return {"remuxed": item.id, "video": "copy" if v_copy else "h264"}
