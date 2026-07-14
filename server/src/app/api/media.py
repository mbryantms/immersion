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
from ..models import MediaRoot

router = APIRouter()

MIME = {".mp4": "video/mp4", ".m4v": "video/mp4", ".webm": "video/webm",
        ".mkv": "video/x-matroska", ".m4a": "audio/mp4", ".jpg": "image/jpeg"}


def safe_resolve(base: Path, relpath: str) -> Path:
    target = (base / relpath).resolve()
    if not target.is_relative_to(base.resolve()):
        raise HTTPException(403, "path escapes root")
    return target


@router.get("/media/thumbs/{name}")
def get_thumb(name: str):
    target = safe_resolve(settings.thumb_dir, name)
    if not target.is_file():
        raise HTTPException(404)
    return FileResponse(target, media_type="image/jpeg")


@router.get("/media/audio/{name}")
def get_audio(name: str):
    """Podcast m4a cache — 'audio' is a reserved pseudo-slug like 'thumbs'."""
    target = safe_resolve(settings.audio_dir, name)
    if not target.is_file():
        raise HTTPException(404)
    return FileResponse(target, media_type="audio/mp4")


@router.get("/media/remux/{name}")
def get_remux(name: str):
    """Browser-safe mp4 cache — 'remux' is a reserved pseudo-slug like 'thumbs'."""
    target = safe_resolve(settings.remux_dir, name)
    if not target.is_file():
        raise HTTPException(404)
    return FileResponse(target, media_type="video/mp4")


@router.get("/media/{root_slug}/{relpath:path}")
def get_media(root_slug: str, relpath: str, session: Session = Depends(get_session)):
    root = session.scalar(select(MediaRoot).where(MediaRoot.slug == root_slug))
    if root is None:
        raise HTTPException(404)
    target = safe_resolve(Path(root.path), relpath)
    if not target.is_file():
        raise HTTPException(404)
    return FileResponse(target, media_type=MIME.get(target.suffix.lower()))
