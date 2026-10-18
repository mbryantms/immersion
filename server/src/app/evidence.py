"""Explainable evidence summaries; no synthetic mastery/confidence score."""

from sqlalchemy import func, select
from .models import LearningEvidence, LexemeExposure


def lexeme_evidence(session, lexeme_id):
    exposure = session.execute(
        select(
            func.count(),
            func.count(func.distinct(LexemeExposure.item_id)),
            func.count(func.distinct(LexemeExposure.day)),
        ).where(LexemeExposure.lexeme_id == lexeme_id)
    ).one()
    rows = session.scalars(
        select(LearningEvidence)
        .where(LearningEvidence.lexeme_id == lexeme_id)
        .order_by(LearningEvidence.ts.desc(), LearningEvidence.id.desc())
        .limit(20)
    ).all()
    return {
        "exposure": {
            "independent_encounters": exposure[0],
            "items": exposure[1],
            "days": exposure[2],
            "policy": "At most one encounter per word/source/UTC day; exposure only",
        },
        "recent_retrieval": [
            {
                "task": row.task,
                "method": row.method,
                "assistance": row.assistance,
                "score": row.score,
                "ts": row.ts,
                "scope": row.scope,
            }
            for row in rows
        ],
        "unassessed": ["pronunciation", "spontaneous_production"],
        "limitation": "Manual marks and Anki intervals are vocabulary familiarity signals; neither measures listening comprehension.",
    }
