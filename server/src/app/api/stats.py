"""Dashboard: transparent activity metrics from the event stream — input
minutes rising, lookup rate falling. No streaks, no composite scores."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from ..db import get_session
from ..models import (
    Event,
    KnowledgeState,
    Lexeme,
    MediaItem,
    ReviewState,
    SavedItem,
    Sentence,
    Setting,
    TokenOccurrence,
)

router = APIRouter()

WEEKS = 8


@router.get("/stats/dashboard")
def dashboard(session: Session = Depends(get_session)):
    now = datetime.now(timezone.utc)
    since = now - timedelta(weeks=WEEKS)

    # input minutes: sum of sentence durations actually played, per ISO week + kind
    rows = session.execute(
        select(Event.ts, Sentence.t0_ms, Sentence.t1_ms, MediaItem.kind)
        .join(Sentence, Sentence.id == Event.sentence_id)
        .join(MediaItem, MediaItem.id == Sentence.item_id)
        .where(Event.type == "sentence_played", Event.ts >= since)
    ).all()
    weekly: dict[str, dict[str, float]] = {}
    for ts, t0, t1, kind in rows:
        ts = ts if ts.tzinfo else ts.replace(tzinfo=timezone.utc)
        iso = ts.isocalendar()
        week = f"{iso.year}-W{iso.week:02d}"
        bucket = weekly.setdefault(week, {"video": 0.0, "audio": 0.0})
        bucket["audio" if kind == "audio" else "video"] += (t1 - t0) / 60000

    # lookup rate + caption dependence per week (per 100 sentences played)
    counts = dict(session.execute(
        select(Event.type, func.count()).where(Event.ts >= since).group_by(Event.type)
    ).all())
    per_week_events = session.execute(
        select(Event.type, Event.ts).where(
            Event.type.in_(("sentence_played", "lookup", "translation_reveal")), Event.ts >= since
        )
    ).all()
    trend: dict[str, dict[str, int]] = {}
    for etype, ts in per_week_events:
        ts = ts if ts.tzinfo else ts.replace(tzinfo=timezone.utc)
        iso = ts.isocalendar()
        week = f"{iso.year}-W{iso.week:02d}"
        trend.setdefault(week, {"sentence_played": 0, "lookup": 0, "translation_reveal": 0})
        trend[week][etype] += 1
    weeks_sorted = sorted(set(weekly) | set(trend))
    week_stats = [
        {
            "week": w,
            "video_minutes": round(weekly.get(w, {}).get("video", 0), 1),
            "audio_minutes": round(weekly.get(w, {}).get("audio", 0), 1),
            "lookup_per_100": _rate(trend.get(w), "lookup"),
            "reveal_per_100": _rate(trend.get(w), "translation_reveal"),
        }
        for w in weeks_sorted
    ]

    # top recurring unknowns: new/learning lexemes by occurrence breadth
    unknown_rows = session.execute(
        select(
            Lexeme.id, Lexeme.simplified, Lexeme.pinyin,
            func.count(TokenOccurrence.lexeme_id).label("occurrences"),
            func.count(func.distinct(TokenOccurrence.item_id)).label("items"),
        )
        .join(TokenOccurrence, TokenOccurrence.lexeme_id == Lexeme.id)
        .join(KnowledgeState, KnowledgeState.lexeme_id == Lexeme.id, isouter=True)
        .where(func.coalesce(KnowledgeState.state, "new").in_(("new", "learning")))
        .where(Lexeme.is_dict.is_(True))
        # HSK 1–2 "unknowns" are almost always cold-start noise (的/我/了…),
        # not real gaps at the levels this library targets
        .where(func.coalesce(Lexeme.hsk_level, 99) >= 3)
        .group_by(Lexeme.id)
        .order_by(func.count(func.distinct(TokenOccurrence.item_id)).desc(),
                  func.count(TokenOccurrence.lexeme_id).desc())
        .limit(10)
    ).all()

    review_due = _review_due_count(session)
    graduated = session.scalar(
        select(func.count()).select_from(ReviewState).where(ReviewState.graduated.is_(True))
    )
    last_import = session.get(Setting, "anki_last_import")
    last_export = session.get(Setting, "anki_last_export")

    return {
        "weeks": week_stats,
        "totals": {
            "lookups": counts.get("lookup", 0),
            "sentences_played": counts.get("sentence_played", 0),
            "saves": counts.get("save", 0) + counts.get("save_sentence", 0),
        },
        "recurring_unknowns": [
            {"lexeme_id": lid, "simplified": simp, "pinyin": pin,
             "occurrences": occ, "items": items}
            for lid, simp, pin, occ, items in unknown_rows
        ],
        "review_due": review_due,
        "graduated_waiting": graduated or 0,
        "anki": {
            "last_import": last_import.value if last_import else None,
            "last_export": last_export.value if last_export else None,
        },
    }


def _rate(bucket: dict | None, key: str) -> float | None:
    if not bucket or not bucket.get("sentence_played"):
        return None
    return round(100 * bucket.get(key, 0) / bucket["sentence_played"], 1)


def _review_due_count(session: Session) -> int:
    now = datetime.now(timezone.utc)
    states = {rs.saved_item_id: rs for rs in session.scalars(select(ReviewState))}
    n = 0
    for (sid,) in session.execute(select(SavedItem.id).where(SavedItem.archived.is_(False))):
        rs = states.get(sid)
        if rs is None:
            n += 1
        elif not rs.graduated:
            due_at = rs.due_at if rs.due_at.tzinfo else rs.due_at.replace(tzinfo=timezone.utc)
            if due_at <= now:
                n += 1
    return n
