"""Seed knowledge_state from Anki card maturity.

Word-level evidence comes from the word-keyed vocab note type (default:
"Xiehanzi Mandarin"): a note's best card interval >= mature_days marks the word
KNOWN, >= 1 day marks it LEARNING. Manual states always win (precedence:
manual > anki > derived); sync never demotes a manual mark."""

from __future__ import annotations

import json
from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.orm import Session

from ..models import KnowledgeState, Setting
from .connect import ac

DEFAULT_QUERY = '"note:Xiehanzi Mandarin"'
FIELD = "Simplified"


def import_known(
    session: Session,
    query: str = DEFAULT_QUERY,
    field: str = FIELD,
    mature_days: int = 21,
    include_suspended: bool = True,
    progress=lambda msg: None,
) -> dict:
    card_ids = ac("findCards", query=query)
    progress(f"{len(card_ids)} cards matched {query}")

    best: dict[str, int] = {}  # simplified -> max interval (days)
    for i in range(0, len(card_ids), 500):
        infos = ac("cardsInfo", cards=card_ids[i : i + 500])
        for c in infos:
            if not include_suspended and c.get("queue") == -1:
                continue
            word = (c.get("fields", {}).get(field) or {}).get("value", "").strip()
            if not word:
                continue
            best[word] = max(best.get(word, 0), int(c.get("interval") or 0))
        progress(f"read {min(i + 500, len(card_ids))}/{len(card_ids)} cards")

    from ..ingest.analysis import get_or_create_lexemes

    lex_ids = get_or_create_lexemes(session, set(best))
    existing = {
        ks.lexeme_id: ks
        for ks in session.scalars(
            select(KnowledgeState).where(KnowledgeState.lexeme_id.in_(list(lex_ids.values())))
        )
    }
    now = datetime.now(timezone.utc)
    counts = {"known": 0, "learning": 0, "unchanged": 0, "manual_kept": 0, "new_cards": 0}
    for word, interval in best.items():
        state = "known" if interval >= mature_days else "learning" if interval >= 1 else None
        if state is None:
            counts["new_cards"] += 1
            continue
        ks = existing.get(lex_ids[word])
        if ks is None:
            session.add(KnowledgeState(
                lexeme_id=lex_ids[word], state=state, source="anki",
                anki_interval_days=interval, updated_at=now,
            ))
            counts[state] += 1
        elif ks.source == "manual":
            counts["manual_kept"] += 1
        elif ks.state != state or ks.anki_interval_days != interval:
            ks.state, ks.source, ks.anki_interval_days, ks.updated_at = state, "anki", interval, now
            counts[state] += 1
        else:
            counts["unchanged"] += 1

    session.merge(Setting(key="anki_last_import", value={
        "at": now.isoformat(), "query": query, "mature_days": mature_days,
        "counts": counts, "words": len(best),
    }))
    session.commit()
    progress(json.dumps(counts))
    return counts
