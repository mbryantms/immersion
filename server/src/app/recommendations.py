"""Local, explainable content estimates. Vocabulary coverage is not comprehension."""

from sqlalchemy import case, func, select
from .models import (
    Event,
    KnowledgeState,
    Sentence,
    Series,
    Setting,
    TextTrack,
    TokenOccurrence,
)


def rank_content(session, candidates, coverage):
    ids = [item.id for item in candidates]
    if not ids:
        return []
    profile_row = session.get(Setting, "learner_profile")
    profile = profile_row.value if profile_row else {}
    goal = profile.get("goal", "listen")
    budget = {"beginner": 3, "intermediate": 7, "advanced": 12}.get(
        profile.get("level"), 7
    )
    # Aggregate once per line, then use a timeline window to expose dense
    # unknown-word stretches without loading the entire token corpus in Python.
    unknown = case(
        (
            TokenOccurrence.lexeme_id.is_not(None)
            & func.coalesce(KnowledgeState.state, "new").in_(("new", "learning")),
            1,
        ),
        else_=0,
    )
    lines = select(
        Sentence.item_id.label("item"),
        Sentence.t0_ms.label("t0"),
        Sentence.t1_ms.label("t1"),
        func.count(TokenOccurrence.lexeme_id).label("tokens"),
        func.coalesce(func.sum(unknown), 0).label("unknown"),
        func.length(Sentence.zh).label("characters"),
    ).select_from(Sentence)
    lines = (
        lines.join(
            TokenOccurrence, TokenOccurrence.sentence_id == Sentence.id, isouter=True
        )
        .join(
            KnowledgeState,
            KnowledgeState.lexeme_id == TokenOccurrence.lexeme_id,
            isouter=True,
        )
        .where(Sentence.item_id.in_(ids))
        .group_by(Sentence.id)
        .subquery()
    )
    stretches = select(
        lines,
        func.sum(lines.c.unknown)
        .over(partition_by=lines.c.item, order_by=lines.c.t0, range_=(0, 30000))
        .label("burst"),
    ).subquery()
    metrics = {
        row.item: row
        for row in session.execute(
            select(
                stretches.c.item,
                func.sum(stretches.c.unknown).label("unknown"),
                func.max(stretches.c.t1).label("end"),
                func.min(stretches.c.t0).label("start"),
                func.max(stretches.c.burst).label("burst"),
                func.sum(stretches.c.characters).label("characters"),
                func.sum(func.max(1, stretches.c.t1 - stretches.c.t0)).label(
                    "spoken_ms"
                ),
            ).group_by(stretches.c.item)
        )
    }
    titles = {s.id: s.title for s in session.scalars(select(Series))}
    sources = {}
    for track in session.scalars(
        select(TextTrack).where(
            TextTrack.item_id.in_(ids), TextTrack.lang == "zh", TextTrack.selected
        )
    ):
        sources[track.item_id] = track.source
    ratings = {}
    for ev in session.scalars(
        select(Event)
        .where(Event.type == "difficulty_rating", Event.study_mode == goal)
        .order_by(Event.ts.desc(), Event.id.desc())
        .limit(1000)
    ):
        ratings.setdefault(ev.item_id, ev.data or {})
    out = []
    for item in candidates:
        c = coverage.get(item.id)
        m = metrics.get(item.id)
        if not c or not m or c["tokens"] == 0:
            continue
        duration = item.duration_ms or max(1, m.end - m.start)
        unknown_rate = round(m.unknown / (duration / 60000), 1)
        speed = round(m.characters / max(1, m.spoken_ms) * 60000)
        source = sources.get(item.id, "unknown")
        source_warning = source in ("whisper", "asr", "unknown")
        rating = ratings.get(item.id, {}).get("rating")
        title = f"{item.title} {titles.get(item.series_id, '')}".casefold()
        interests = [
            str(x) for x in profile.get("interests", []) if str(x).casefold() in title
        ]
        # Relative ordering only. No scientifically validated universal cutoff.
        score = unknown_rate / max(1, budget) + (m.burst or 0) / max(6, budget * 2)
        if goal != "read":
            score += max(0, speed - 220) / 220
        score += 0.5 if source_warning else 0
        score -= 0.75 if interests else 0
        score += {"too_hard": 2, "manageable": -1, "too_easy": 0.5}.get(rating, 0)
        reasons = [
            f"{unknown_rate} unfamiliar token occurrences/min",
            f"{m.burst or 0} unfamiliar tokens in the densest 30-second cue-start window",
        ]
        if interests:
            reasons.append("Matches a topic in your title preferences")
        if rating:
            reasons.append(f"Your {goal} rating: {rating.replace('_', ' ')}")
        out.append(
            (
                score,
                item,
                {
                    **c,
                    "unknowns_per_minute": unknown_rate,
                    "dense_unknowns_30s": m.burst or 0,
                    "subtitle_characters_per_minute": speed,
                    "subtitle_source": source,
                    "source_warning": source_warning,
                    "goal": goal,
                    "reasons": reasons,
                    "difficulty_rating": rating,
                    "uncertainty": "Estimated from vocabulary marks and subtitle timing; grammar, audio clarity and actual comprehension are unmeasured.",
                },
            )
        )
    out.sort(
        key=lambda entry: (
            entry[0],
            entry[1].series_id or 0,
            entry[1].ordinal or 0,
            entry[1].id,
        )
    )
    return out
