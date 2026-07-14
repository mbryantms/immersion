"""Analyzed transcript payload + word lookup + lexeme detail.

The sentences payload is immutable per content revision and cached hard by the
client; mutable learner state ships separately (see knowledge.py) so a save
never invalidates the transcript cache."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..db import get_session
from ..lingua.convert import zh_norm
from ..models import (
    AnkiSentence,
    KnowledgeState,
    Lexeme,
    LexemeStats,
    MediaItem,
    SavedItem,
    Sense,
    Sentence,
    TextTrack,
)

router = APIRouter()


def _anki_matches(session: Session, rows: list[Sentence]) -> set[int]:
    """Sentence ids that already exist as Anki cards (matched on normalized zh)."""
    norm_to_id = {zh_norm(s.zh): s.id for s in rows}
    keys = list(norm_to_id)
    hits: set[int] = set()
    for i in range(0, len(keys), 900):
        for (norm,) in session.execute(
            select(AnkiSentence.zh_norm).where(AnkiSentence.zh_norm.in_(keys[i : i + 900]))
        ):
            hits.add(norm_to_id[norm])
    return hits


@router.get("/items/{item_id}/sentences")
def get_sentences(item_id: int, session: Session = Depends(get_session)):
    if session.get(MediaItem, item_id) is None:
        raise HTTPException(404)
    rows = session.scalars(
        select(Sentence).where(Sentence.item_id == item_id).order_by(Sentence.ordinal)
    ).all()
    # user-set per-track sync nudge shifts display timing; cue times stay pristine
    offsets = dict(session.execute(
        select(TextTrack.id, TextTrack.offset_ms).where(TextTrack.item_id == item_id)
    ).all())
    in_anki = _anki_matches(session, rows)
    return {
        "item_id": item_id,
        "sentences": [
            {
                "id": s.id, "ord": s.ordinal, "zh": s.zh, "tr": s.trad,
                "t0": max(0, s.t0_ms + offsets.get(s.track_id, 0)),
                "t1": max(0, s.t1_ms + offsets.get(s.track_id, 0)),
                "en": s.en, "conf": s.align_conf,
                "anki": s.id in in_anki or None,
                "words": (s.analysis or {}).get("words", []),
            }
            for s in rows
        ],
    }


@router.post("/sentences/{sentence_id}/explain")
def explain(sentence_id: int, session: Session = Depends(get_session)):
    """AI explanation (cached per zh text + prompt version). Runs the provider
    synchronously — seconds, not the job queue; provenance travels with it."""
    from ..ai import provider
    from ..ai.tasks import explain_sentence

    sentence = session.get(Sentence, sentence_id)
    if sentence is None:
        raise HTTPException(404)
    if not provider.available():
        raise HTTPException(503, "AI provider unavailable (claude CLI not on PATH)")
    artifact = explain_sentence(session, sentence)
    return {
        **artifact.output,
        "provider": artifact.provider,
        "model": artifact.model,
        "created_at": artifact.created_at,
    }


class LookupIn(BaseModel):
    sentence_id: int
    start: int
    end: int


def _lexeme_payload(session: Session, lex: Lexeme, max_senses: int = 8) -> dict:
    senses = session.scalars(
        select(Sense).where(Sense.lexeme_id == lex.id).order_by(Sense.ord).limit(max_senses)
    ).all()
    state = session.get(KnowledgeState, lex.id)
    saved = session.scalar(
        select(SavedItem.id).where(SavedItem.lexeme_id == lex.id, SavedItem.archived.is_(False))
    )
    return {
        "lexeme_id": lex.id, "simplified": lex.simplified, "traditional": lex.traditional,
        "pinyin": lex.pinyin, "hsk": lex.hsk_level, "is_dict": lex.is_dict,
        "pos": lex.pos, "freq_rank": lex.freq_rank,
        "senses": [{"py": s.pinyin, "trad": s.traditional, "defs": s.glosses} for s in senses],
        "state": state.state if state else "new",
        "state_source": state.source if state else None,
        "saved_item_id": saved,
    }


@router.post("/lookup")
def lookup(body: LookupIn, session: Session = Depends(get_session)):
    """Ranked lexical candidates for a character span (custom-span rescue:
    exact span first, then every dictionary word contained in it)."""
    sentence = session.get(Sentence, body.sentence_id)
    if sentence is None:
        raise HTTPException(404)
    span = sentence.zh[body.start : body.end]
    if not span or len(span) > 12:
        raise HTTPException(400, "bad span")
    subs = {span[i:j] for i in range(len(span)) for j in range(i + 1, len(span) + 1)}
    lexes = session.scalars(select(Lexeme).where(Lexeme.simplified.in_(list(subs)))).all()
    lexes.sort(key=lambda l: (l.simplified != span, -len(l.simplified)))
    return {
        "span": span,
        "candidates": [_lexeme_payload(session, l) for l in lexes[:10]],
    }


@router.get("/lexemes/{lexeme_id}")
def get_lexeme(lexeme_id: int, session: Session = Depends(get_session)):
    lex = session.get(Lexeme, lexeme_id)
    if lex is None:
        raise HTTPException(404)
    stats = session.get(LexemeStats, lexeme_id)
    payload = _lexeme_payload(session, lex)
    payload["stats"] = {
        "encounters": stats.encounters if stats else 0,
        "lookups": stats.lookups if stats else 0,
        "first_seen": stats.first_seen if stats else None,
        "last_seen": stats.last_seen if stats else None,
    }
    return payload
