"""Library browsing: roots, series, items, coverage."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from urllib.parse import quote

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import case, func, select
from sqlalchemy.orm import Session

from ..db import get_session
from ..jobs import enqueue
from ..models import (
    Event,
    KnowledgeState,
    MediaItem,
    MediaRoot,
    PlaybackProgress,
    Sentence,
    Series,
    TextTrack,
    TokenOccurrence,
)

router = APIRouter()


def stream_url(item: MediaItem, root_slug: str) -> str:
    # audio items stream the ingest-transcoded m4a (sample-accurate seeking),
    # never the original file under the root
    if item.kind == "audio":
        return f"/media/audio/{item.id}.m4a"
    # non-direct-play video streams its cached remux once the fp matches
    if ((item.meta or {}).get("remux") or {}).get("fp") == item.fingerprint:
        return f"/media/remux/{item.id}.mp4"
    return f"/media/{root_slug}/{quote(item.relpath)}"


def coverage_by_item(session: Session, item_ids: list[int]) -> dict[int, dict]:
    """item_id -> {coverage, tokens, unknown_lexemes}; coverage counts known +
    familiar (passively-acquired, derive.py) tokens over non-ignored tokens."""
    if not item_ids:
        return {}
    known = case((KnowledgeState.state.in_(("known", "familiar")), 1), else_=0)
    ignored = case((KnowledgeState.state == "ignored", 1), else_=0)
    unknown_lex = case(
        (func.coalesce(KnowledgeState.state, "new").in_(("new", "learning")), TokenOccurrence.lexeme_id)
    )
    rows = session.execute(
        select(
            TokenOccurrence.item_id,
            func.count().label("total"),
            func.sum(known).label("known"),
            func.sum(ignored).label("ignored"),
            func.count(func.distinct(unknown_lex)).label("unknown_lexemes"),
        )
        .join(KnowledgeState, KnowledgeState.lexeme_id == TokenOccurrence.lexeme_id, isouter=True)
        .where(TokenOccurrence.item_id.in_(item_ids))
        .group_by(TokenOccurrence.item_id)
    ).all()
    out = {}
    for item_id, total, known_n, ignored_n, unknown_n in rows:
        denom = max(1, total - (ignored_n or 0))
        out[item_id] = {
            "coverage": round((known_n or 0) / denom, 4),
            "tokens": total,
            "unknown_lexemes": unknown_n or 0,
        }
    return out


class RootIn(BaseModel):
    slug: str
    kind: str = "video"
    path: str
    include_glob: str | None = None


def coverage_by_series(session: Session) -> dict[int, float]:
    """series_id -> known+familiar token share (non-ignored denominator)."""
    known = case((KnowledgeState.state.in_(("known", "familiar")), 1), else_=0)
    ignored = case((KnowledgeState.state == "ignored", 1), else_=0)
    rows = session.execute(
        select(MediaItem.series_id, func.count(), func.sum(known), func.sum(ignored))
        .select_from(TokenOccurrence)
        .join(MediaItem, MediaItem.id == TokenOccurrence.item_id)
        .join(KnowledgeState, KnowledgeState.lexeme_id == TokenOccurrence.lexeme_id, isouter=True)
        .where(MediaItem.series_id.is_not(None))
        .group_by(MediaItem.series_id)
    ).all()
    return {
        sid: round((known_n or 0) / max(1, total - (ignored_n or 0)), 4)
        for sid, total, known_n, ignored_n in rows
    }


@router.get("/library")
def get_library(session: Session = Depends(get_session)):
    roots = session.scalars(select(MediaRoot)).all()
    root_kind = {r.id: r.kind for r in roots}
    series = session.scalars(select(Series)).all()
    coverage = coverage_by_series(session)
    counts = dict(session.execute(
        select(MediaItem.series_id, func.count()).where(MediaItem.available).group_by(MediaItem.series_id)
    ).all())
    ready_counts = dict(session.execute(
        select(MediaItem.series_id, func.count())
        .where(MediaItem.available, MediaItem.ready)
        .group_by(MediaItem.series_id)
    ).all())
    cont = session.execute(
        select(PlaybackProgress, MediaItem)
        .join(MediaItem, MediaItem.id == PlaybackProgress.item_id)
        .where(PlaybackProgress.completed.is_(False), PlaybackProgress.position_ms > 0)
        .order_by(PlaybackProgress.updated_at.desc())
        .limit(12)
    ).all()
    return {
        "roots": [
            {"id": r.id, "slug": r.slug, "kind": r.kind, "path": r.path,
             "include_glob": r.include_glob, "enabled": r.enabled,
             "last_scan_at": r.last_scan_at}
            for r in roots
        ],
        "series": [
            {"id": s.id, "root_id": s.root_id, "kind": root_kind.get(s.root_id, "video"),
             "title": s.title, "level": s.level_hint,
             "episodes": counts.get(s.id, 0), "ready": ready_counts.get(s.id, 0),
             "coverage": coverage.get(s.id),
             "cover_url": f"/media/thumbs/{s.cover_item_id}.jpg?v=2" if s.cover_item_id else None}
            for s in series
            if counts.get(s.id, 0) > 0
        ],
        "continue": [
            {"item_id": i.id, "title": i.title, "series_id": i.series_id,
             "position_ms": p.position_ms, "duration_ms": i.duration_ms,
             "thumb_url": f"/media/thumbs/{i.id}.jpg?v=2", "updated_at": p.updated_at}
            for p, i in cont
        ],
    }


@router.get("/recommendations")
def recommendations(session: Session = Depends(get_session)):
    """i+1 picks: ready, unfinished items whose known+familiar coverage sits in
    the comprehension sweet spot — hard enough to feed acquisition, easy enough
    to follow. Sorted by closeness to the target, ties broken by series order."""
    LOW, TARGET, HIGH = 0.88, 0.95, 0.985
    items = session.scalars(
        select(MediaItem).where(MediaItem.available, MediaItem.ready)
    ).all()
    completed = {
        p.item_id
        for p in session.scalars(select(PlaybackProgress).where(PlaybackProgress.completed))
    }
    candidates = [i for i in items if i.id not in completed]
    cov = coverage_by_item(session, [i.id for i in candidates])
    scored = [
        (abs(cov[i.id]["coverage"] - TARGET), i, cov[i.id])
        for i in candidates
        if i.id in cov and LOW <= cov[i.id]["coverage"] <= HIGH
    ]
    fallback = not scored
    if fallback:
        # cold start: nothing reaches the band yet (young knowledge base) —
        # the most-familiar unfinished items are still the best next input
        scored = [
            (1 - cov[i.id]["coverage"], i, cov[i.id])
            for i in candidates if i.id in cov
        ]
    scored.sort(key=lambda t: (t[0], t[1].series_id or 0, t[1].ordinal or 0))
    series_titles = {s.id: s.title for s in session.scalars(select(Series))}
    return {
        "band": {"low": LOW, "high": HIGH},
        "fallback": fallback,
        "items": [
            {
                "item_id": i.id, "title": i.title, "kind": i.kind,
                "series_id": i.series_id,
                "series_title": series_titles.get(i.series_id),
                "ordinal": i.ordinal,
                "duration_ms": i.duration_ms,
                "thumb_url": f"/media/thumbs/{i.id}.jpg?v=2",
                "coverage": c["coverage"],
                "unknown_lexemes": c["unknown_lexemes"],
            }
            for _, i, c in scored[:6]
        ],
    }


@router.post("/roots")
def add_root(body: RootIn, session: Session = Depends(get_session)):
    if body.slug in ("thumbs", "audio") or "/" in body.slug or not body.slug.isascii():
        raise HTTPException(400, "invalid slug")
    if session.scalar(select(MediaRoot).where(MediaRoot.slug == body.slug)):
        raise HTTPException(409, "slug exists")
    root = MediaRoot(slug=body.slug, kind=body.kind, path=body.path, include_glob=body.include_glob)
    session.add(root)
    session.commit()
    enqueue(session, "scan_root", {"root_id": root.id})
    return {"id": root.id}


@router.get("/series/{series_id}")
def get_series(series_id: int, session: Session = Depends(get_session)):
    series = session.get(Series, series_id)
    if series is None:
        raise HTTPException(404)
    items = session.scalars(
        select(MediaItem)
        .where(MediaItem.series_id == series_id)
        .order_by(MediaItem.ordinal, MediaItem.title)
    ).all()
    progress = {
        p.item_id: p
        for p in session.scalars(
            select(PlaybackProgress).where(PlaybackProgress.item_id.in_([i.id for i in items]))
        )
    }
    has_zh = {
        t
        for (t,) in session.execute(
            select(TextTrack.item_id).where(
                TextTrack.item_id.in_([i.id for i in items]),
                TextTrack.lang == "zh", TextTrack.selected,
            )
        )
    }
    cov = coverage_by_item(session, [i.id for i in items if i.ready])
    return {
        "id": series.id, "title": series.title, "level": series.level_hint,
        "items": [
            {
                "id": i.id, "title": i.title, "ordinal": i.ordinal,
                "duration_ms": i.duration_ms, "ready": i.ready, "available": i.available,
                "has_zh": i.id in has_zh,
                "thumb_url": f"/media/thumbs/{i.id}.jpg?v=2",
                "position_ms": progress[i.id].position_ms if i.id in progress else 0,
                "completed": progress[i.id].completed if i.id in progress else False,
                **cov.get(i.id, {}),
            }
            for i in items
        ],
    }


@router.get("/items/{item_id}")
def get_item(item_id: int, session: Session = Depends(get_session)):
    item = session.get(MediaItem, item_id)
    if item is None:
        raise HTTPException(404)
    root = session.get(MediaRoot, item.root_id)
    series = session.get(Series, item.series_id) if item.series_id else None
    progress = session.get(PlaybackProgress, item_id)
    tracks = session.scalars(select(TextTrack).where(TextTrack.item_id == item_id)).all()
    n_sentences = session.scalar(
        select(func.count()).select_from(Sentence).where(Sentence.item_id == item_id)
    )
    cov = coverage_by_item(session, [item_id]) if item.ready else {}
    siblings = []
    if item.series_id:
        siblings = session.execute(
            select(MediaItem.id, MediaItem.ordinal)
            .where(MediaItem.series_id == item.series_id, MediaItem.available)
            .order_by(MediaItem.ordinal, MediaItem.title)
        ).all()
    ids = [s.id for s in siblings]
    pos = ids.index(item_id) if item_id in ids else -1

    # captions-off rewatch nudge: mastered content, watched through, and barely
    # any recent dictionary reliance — suggest rewatching without subtitles
    coverage = cov.get(item_id, {}).get("coverage", 0)
    rewatch_nudge = False
    if item.ready and progress is not None and progress.completed and coverage >= 0.95:
        recent_lookups = session.scalar(
            select(func.count()).select_from(Event).where(
                Event.type == "lookup", Event.item_id == item_id,
                Event.ts >= datetime.now(timezone.utc) - timedelta(days=14),
            )
        )
        rewatch_nudge = (recent_lookups or 0) < 5

    return {
        "id": item.id, "title": item.title, "kind": item.kind, "ordinal": item.ordinal,
        "duration_ms": item.duration_ms, "ready": item.ready, "available": item.available,
        "width": item.width, "height": item.height,
        "series": {"id": series.id, "title": series.title, "level": series.level_hint} if series else None,
        "stream_url": stream_url(item, root.slug),
        "thumb_url": f"/media/thumbs/{item.id}.jpg?v=2",
        "tracks": [
            {"id": t.id, "lang": t.lang, "source": t.source, "format": t.format,
             "offset_ms": t.offset_ms, "selected": t.selected}
            for t in tracks
        ],
        "n_sentences": n_sentences,
        "progress": {
            "position_ms": progress.position_ms if progress else 0,
            "completed": progress.completed if progress else False,
            "subtitle_mode": progress.subtitle_mode if progress else None,
        },
        "prev_item_id": ids[pos - 1] if pos > 0 else None,
        "next_item_id": ids[pos + 1] if 0 <= pos < len(ids) - 1 else None,
        "rewatch_nudge": rewatch_nudge,
        **cov.get(item_id, {}),
    }


class TrackPatch(BaseModel):
    offset_ms: int


@router.patch("/tracks/{track_id}")
def patch_track(track_id: int, body: TrackPatch, session: Session = Depends(get_session)):
    """Per-track sync nudge; applied to sentence times in the sentences payload."""
    track = session.get(TextTrack, track_id)
    if track is None:
        raise HTTPException(404)
    track.offset_ms = max(-30_000, min(30_000, body.offset_ms))
    session.commit()
    return {"id": track.id, "offset_ms": track.offset_ms}


@router.post("/items/{item_id}/transcribe")
def transcribe_item(item_id: int, session: Session = Depends(get_session)):
    """Queue whisper transcript generation for an unsubbed video."""
    item = session.get(MediaItem, item_id)
    if item is None:
        raise HTTPException(404)
    if item.kind != "video":
        raise HTTPException(400, "podcasts align via their transcript")
    job = enqueue(session, "whisper_transcribe", {"item_id": item_id})
    return {"queued": job is not None}
