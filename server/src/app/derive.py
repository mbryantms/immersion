"""Passive-exposure knowledge derivation.

The app's premise is acquisition through repeated comprehensible encounters,
so absence of struggle IS evidence: a word met again and again, across many
shows, over weeks, without ever being looked up, is a word the learner knows.
This job reads the counters the event stream already maintains (LexemeStats +
lookup events) and promotes:

  new      -> familiar   (moderate evidence)
  familiar -> known      (deep evidence)

Rules (all conditions must hold; thresholds deliberately conservative because
false positives are cheap — any lookup instantly demotes back to learning,
see api/events.py):

  familiar: >=12 encounters, >=3 distinct items, first->last seen span >=14d,
            no lookup in the last 30 days
  known:    >=25 encounters, >=5 distinct items, span >=30d,
            no lookup in the last 60 days

Never touches manual or anki states (stronger evidence), never demotes, and
skips lexemes with an active word save — those are the review funnel's
business until they graduate. Runs nightly from the worker loop; idempotent.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from .models import Event, KnowledgeState, Lexeme, LexemeStats, SavedItem

FAMILIAR = {"encounters": 12, "items": 3, "span_days": 14, "quiet_days": 30}
KNOWN = {"encounters": 25, "items": 5, "span_days": 30, "quiet_days": 60}

_RANK = {"new": 0, "familiar": 1, "known": 2}


def _aware(ts: datetime | None) -> datetime | None:
    if ts is None:
        return None
    return ts if ts.tzinfo else ts.replace(tzinfo=timezone.utc)


def _meets(stats: LexemeStats, rule: dict, last_lookup: datetime | None, now: datetime) -> bool:
    first, last = _aware(stats.first_seen), _aware(stats.last_seen)
    if stats.encounters < rule["encounters"] or (stats.distinct_items or 0) < rule["items"]:
        return False
    if not first or not last or (last - first) < timedelta(days=rule["span_days"]):
        return False
    if last_lookup and (now - last_lookup) < timedelta(days=rule["quiet_days"]):
        return False
    return True


def derive_knowledge(session: Session, progress=lambda msg: None) -> dict:
    now = datetime.now(timezone.utc)
    last_lookup = {
        lex_id: _aware(ts)
        for lex_id, ts in session.execute(
            select(Event.lexeme_id, func.max(Event.ts))
            .where(Event.type == "lookup", Event.lexeme_id.is_not(None))
            .group_by(Event.lexeme_id)
        )
    }
    active_saves = {
        lex_id
        for (lex_id,) in session.execute(
            select(SavedItem.lexeme_id).where(
                SavedItem.kind == "word",
                SavedItem.archived.is_(False),
                SavedItem.lexeme_id.is_not(None),
            )
        )
    }

    rows = session.execute(
        select(LexemeStats, KnowledgeState)
        .join(Lexeme, Lexeme.id == LexemeStats.lexeme_id)
        .join(KnowledgeState, KnowledgeState.lexeme_id == LexemeStats.lexeme_id, isouter=True)
        .where(Lexeme.is_dict.is_(True))
        .where(LexemeStats.encounters >= FAMILIAR["encounters"])
    ).all()

    counts = {"familiar": 0, "known": 0, "checked": len(rows)}
    for stats, ks in rows:
        if ks is not None and ks.source in ("manual", "anki"):
            continue  # stronger evidence owns this word
        if ks is not None and ks.state == "ignored":
            continue
        if stats.lexeme_id in active_saves:
            continue  # the review funnel's business until graduation
        # derived 'learning' (a lookup demotion) re-earns promotion once the
        # quiet window passes — that's the self-correction loop working

        current = ks.state if ks is not None else "new"
        lookup_ts = last_lookup.get(stats.lexeme_id)
        target = None
        if _meets(stats, KNOWN, lookup_ts, now):
            target = "known"
        elif _meets(stats, FAMILIAR, lookup_ts, now):
            target = "familiar"
        if target is None or _RANK.get(target, 0) <= _RANK.get(current, 0):
            continue  # no promotion (never demote here)

        if ks is None:
            session.add(KnowledgeState(
                lexeme_id=stats.lexeme_id, state=target, source="derived", updated_at=now,
            ))
        else:
            ks.state, ks.source, ks.updated_at = target, "derived", now
        session.add(Event(
            type="knowledge_derived", lexeme_id=stats.lexeme_id,
            data={"state": target, "encounters": stats.encounters,
                  "items": stats.distinct_items,
                  "last_lookup": lookup_ts.isoformat() if lookup_ts else None},
        ))
        counts[target] += 1

    session.commit()
    progress(f"promoted {counts['familiar']} familiar, {counts['known']} known")
    return counts
