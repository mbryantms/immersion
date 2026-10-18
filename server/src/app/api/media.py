"""File serving under /media/*.

In production Caddy owns /media/* (file_server per root + thumbs) and these
routes are never reached; in `vite dev` the proxy sends /media here. Path
resolution refuses traversal and symlink escape from the configured root."""

from __future__ import annotations

from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import FileResponse
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..config import settings
from ..db import get_session
from ..models import MediaRoot, MediaItem

router = APIRouter()

MIME = {".mp4": "video/mp4", ".m4v": "video/mp4", ".webm": "video/webm",
        ".mkv": "video/x-matroska", ".m4a": "audio/mp4", ".jpg": "image/jpeg"}


def safe_resolve(base: Path, relpath: str) -> Path:
    target = (base / relpath).resolve()
    if not target.is_relative_to(base.resolve()):
        raise HTTPException(403, "path escapes root")
    return target


def _cache_item(session: Session, name: str, suffix: str) -> MediaItem:
    if not name.endswith(suffix) or not name[:-len(suffix)].isdigit():
        raise HTTPException(404)
    item = session.get(MediaItem, int(name[:-len(suffix)]))
    if item is None or not item.available:
        raise HTTPException(404)
    return item


@router.get("/media/thumbs/{name}")
def get_thumb(name: str):
    target = safe_resolve(settings.thumb_dir, name)
    if not target.is_file():
        raise HTTPException(404)
    return FileResponse(target, media_type="image/jpeg", headers={"Cache-Control": "private, no-cache"})


@router.get("/media/audio/{name}")
def get_audio(name: str, v: str | None = None, session: Session = Depends(get_session)):
    """Podcast m4a cache — 'audio' is a reserved pseudo-slug like 'thumbs'."""
    item = _cache_item(session, name, ".m4a")
    meta = item.meta or {}
    if meta.get("m4a_fp") != item.fingerprint or (v is not None and v != str(meta.get("m4a_revision", item.fingerprint or "legacy"))):
        raise HTTPException(409, "Audio cache changed; reload the player or repair playback")
    target = safe_resolve(settings.audio_dir, name)
    if not target.is_file():
        raise HTTPException(404)
    return FileResponse(target, media_type="audio/mp4", headers={"Cache-Control": "private, no-cache"})


@router.get("/media/remux/{name}")
def get_remux(name: str, v: str | None = None, session: Session = Depends(get_session)):
    """Browser-safe mp4 cache — 'remux' is a reserved pseudo-slug like 'thumbs'."""
    item = _cache_item(session, name, ".mp4")
    from ..ingest.remux import remux_current
    meta = (item.meta or {}).get("remux") or {}
    if not remux_current(item) or (v is not None and v != str(meta.get("revision", item.fingerprint or "legacy"))):
        raise HTTPException(409, "Playback cache changed; reload the player or repair playback")
    target = safe_resolve(settings.remux_dir, name)
    if not target.is_file():
        raise HTTPException(404)
    return FileResponse(target, media_type="video/mp4", headers={"Cache-Control": "private, no-cache"})


@router.get("/media/{root_slug}/{relpath:path}")
def get_media(root_slug: str, relpath: str, session: Session = Depends(get_session)):
    root = session.scalar(select(MediaRoot).where(MediaRoot.slug == root_slug))
    if root is None:
        raise HTTPException(404)
    target = safe_resolve(Path(root.path), relpath)
    if not target.is_file():
        raise HTTPException(404)
    return FileResponse(target, media_type=MIME.get(target.suffix.lower()), headers={"Cache-Control": "private, no-cache"})
