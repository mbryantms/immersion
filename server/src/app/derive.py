"""Repeated exposure estimates familiarity; it never establishes mastery.

Only source/day-deduplicated encounters from the evidence policy count.
Legacy playback counters remain visible but cannot silently promote words.
Lookups are exploration, not automatic evidence of failure.
"""

from datetime import datetime, timedelta, timezone

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from .models import Event, KnowledgeState, Lexeme, LexemeExposure, SavedItem

FAMILIAR = {"encounters": 12, "items": 3, "span_days": 14}


def derive_knowledge(session: Session, progress=lambda msg: None) -> dict:
    rows = session.execute(
        select(
            LexemeExposure.lexeme_id,
            func.count(),
            func.count(func.distinct(LexemeExposure.item_id)),
            func.min(LexemeExposure.ts),
            func.max(LexemeExposure.ts),
        )
        .join(Lexeme, Lexeme.id == LexemeExposure.lexeme_id)
        .where(Lexeme.is_dict.is_(True))
        .group_by(LexemeExposure.lexeme_id)
        .having(func.count() >= FAMILIAR["encounters"])
    ).all()
    active_saves = set(
        session.scalars(
            select(SavedItem.lexeme_id).where(
                SavedItem.kind == "word", SavedItem.archived.is_(False)
            )
        )
    )
    counts = {"familiar": 0, "known": 0, "checked": len(rows)}
    for lid, encounters, items, first, last in rows:
        ks = session.get(KnowledgeState, lid)
        if ks and (
            ks.source != "derived" or ks.state in ("ignored", "familiar", "known")
        ):
            continue
        if (
            lid in active_saves
            or items < FAMILIAR["items"]
            or last - first < timedelta(days=FAMILIAR["span_days"])
        ):
            continue
        now = datetime.now(timezone.utc)
        if ks is None:
            session.add(
                KnowledgeState(
                    lexeme_id=lid, state="familiar", source="derived", updated_at=now
                )
            )
        else:
            ks.state, ks.updated_at = "familiar", now
        session.add(
            Event(
                type="knowledge_derived",
                lexeme_id=lid,
                data={
                    "state": "familiar",
                    "encounters": encounters,
                    "items": items,
                    "policy": "evidence-v1",
                    "interpretation": "exposure_only",
                },
            )
        )
        counts["familiar"] += 1
    session.commit()
    progress(
        f"estimated familiarity for {counts['familiar']} words; no mastery inferred"
    )
    return counts
