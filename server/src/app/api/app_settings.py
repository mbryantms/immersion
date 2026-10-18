"""Key-value app settings (playback defaults, Anki thresholds, ...) and
dictionary-layer introspection for the Settings page."""

from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlalchemy import func, select
from pydantic import BaseModel, Field
from typing import Literal
from sqlalchemy.orm import Session

from ..db import get_session
from ..models import Lexeme, Sense, Setting

router = APIRouter()


@router.get("/dictionaries")
def dictionaries(session: Session = Depends(get_session)):
    """What the dictionary layer loaded. sense.source keys future additions
    (CedPane proper nouns, Unihan character data, user edits, AI)."""
    by_source = dict(session.execute(
        select(Sense.source, func.count()).group_by(Sense.source)
    ).all())
    hsk_tagged = session.scalar(
        select(func.count()).select_from(Lexeme).where(Lexeme.hsk_level.is_not(None))
    )
    names = {"cedict": "CC-CEDICT", "user": "Your edits", "ai": "AI-generated"}
    dicts = [
        {"name": names.get(src, src), "entries": n, "source": f"sense.source={src}"}
        for src, n in sorted(by_source.items())
    ]
    dicts.append({"name": "HSK 3.0 wordlist", "entries": hsk_tagged or 0, "source": "hsk30.json"})
    return {
        "dictionaries": dicts,
        "lexemes": session.scalar(select(func.count()).select_from(Lexeme)),
        "oov_lexemes": session.scalar(
            select(func.count()).select_from(Lexeme).where(Lexeme.is_dict.is_(False))
        ),
    }


@router.get("/settings")
def get_settings(session: Session = Depends(get_session)):
    return {s.key: s.value for s in session.scalars(select(Setting))}


@router.put("/settings")
def put_settings(body: dict, session: Session = Depends(get_session)):
    for key, value in body.items():
        session.merge(Setting(key=key, value=value))
    session.commit()
    return {"ok": True}


class LearnerProfile(BaseModel):
    goal: Literal["read", "listen", "dictate"] = "listen"
    level: Literal["unknown", "beginner", "intermediate", "advanced"] = "unknown"
    script: Literal["source", "simplified", "traditional"] = "source"
    interests: list[str] = Field(default_factory=list, max_length=10)


@router.get("/learner-profile")
def get_learner_profile(session: Session = Depends(get_session)):
    row = session.get(Setting, "learner_profile")
    return LearnerProfile.model_validate(row.value if row else {}).model_dump()


@router.put("/learner-profile")
def put_learner_profile(body: LearnerProfile, session: Session = Depends(get_session)):
    data = body.model_dump()
    data["interests"] = [interest.strip()[:80] for interest in body.interests if interest.strip()]
    session.merge(Setting(key="learner_profile", value=data))
    session.commit()
    return data
