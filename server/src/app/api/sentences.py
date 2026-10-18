"""Analyzed transcript payload + word lookup + lexeme detail.

The sentences payload is immutable per content revision and cached hard by the
client; mutable learner state ships separately (see knowledge.py) so a save
never invalidates the transcript cache."""

from __future__ import annotations

import hashlib
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Request, Response
from pydantic import BaseModel
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from ..db import get_session
from ..lingua.convert import zh_norm, t2s
from ..lingua.script_policy import script_variants
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
    SentenceIdentity,
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


def _slim_words(analysis: dict | None, source: str | None = None) -> list[dict]:
    """Trim inline CEDICT glosses to one sense / two defs: full glosses are
    ~60% of the payload, but the gloss sheet only needs an instant placeholder
    until /lexemes/{id} returns the real entry."""
    out = []
    cursor = 0
    for w in (analysis or {}).get("words", []):
        if source is not None and "start" not in w:
            start = source.find(w["t"], cursor)
            if start >= 0:
                w = {**w, "start": start, "end": start + len(w["t"])}
                cursor = w["end"]
        else:
            cursor = w.get("end", cursor)
        gloss = w.get("gloss")
        if gloss:
            first = gloss[0]
            w = {**w, "gloss": [{"py": first.get("py"), "defs": (first.get("defs") or [])[:2]}]}
        out.append(w)
    return out


@router.get("/items/{item_id}/sentences")
def get_sentences(
    item_id: int,
    request: Request,
    response: Response,
    session: Session = Depends(get_session),
):
    item = session.get(MediaItem, item_id)
    if item is None:
        raise HTTPException(404)
    # user-set per-track sync nudge shifts display timing; cue times stay pristine
    offsets = dict(
        session.execute(
            select(TextTrack.id, TextTrack.offset_ms).where(TextTrack.item_id == item_id)
        ).all()
    )

    # the payload is immutable per (content revision, offsets, anki import) —
    # a cheap ETag turns every reopen into a 304 instead of a re-download;
    # analysis_rev covers in-place reanalysis, which keeps sentence ids
    rev = (item.meta or {}).get("analysis_rev", 0)
    identity_revision = session.scalar(
        select(func.coalesce(func.sum(SentenceIdentity.revision), 0)).where(
            SentenceIdentity.item_id == item_id
        )
    )
    max_id, n = session.execute(
        select(func.max(Sentence.id), func.count()).where(Sentence.item_id == item_id)
    ).one()
    from ..models import Setting

    anki_stamp = session.get(Setting, "anki_last_import")
    stamp = ((anki_stamp.value or {}) if anki_stamp else {}).get("at", "")
    etag = (
        'W/"'
        + hashlib.sha1(
            f"{item_id}:{max_id}:{n}:{rev}:{identity_revision}:{sorted(offsets.items())}:{stamp}".encode()
        ).hexdigest()[:20]
        + '"'
    )
    if request.headers.get("if-none-match") == etag:
        return Response(status_code=304)
    response.headers["ETag"] = etag
    response.headers["Cache-Control"] = "private, no-cache"  # cache, but revalidate

    rows = session.scalars(
        select(Sentence).where(Sentence.item_id == item_id).order_by(Sentence.ordinal)
    ).all()
    in_anki = _anki_matches(session, rows)
    identities = {
        identity.id: identity
        for identity in session.scalars(
            select(SentenceIdentity).where(SentenceIdentity.item_id == item_id)
        )
    }
    tracks = {
        track.id: track
        for track in session.scalars(select(TextTrack).where(TextTrack.item_id == item_id))
    }

    def provenance(sentence):
        identity = identities.get(sentence.id)
        overrides = (identity.overrides or {}) if identity else {}
        track = tracks.get(sentence.track_id)
        return {
            "text_source": "corrected"
            if "zh" in overrides
            else track.source
            if track
            else "unknown",
            "translation_source": sentence.en_source,
            "timing_source": "corrected"
            if "t0_ms" in overrides or "t1_ms" in overrides
            else "estimated"
            if track
            and (
                track.source == "whisper"
                or (track.source == "transcript" and track.format != "srt")
            )
            else "source cues",
            "alignment_quality": identity.source.get("timing_quality") if identity else None,
            "temporal_coverage": sentence.align_conf,
            "revision": identity.revision if identity else 0,
        }

    return {
        "item_id": item_id,
        # the offset baked into these times; the client shifts live nudges
        # relative to this instead of refetching the whole transcript
        "zh_offset_ms": offsets.get(rows[0].track_id, 0) if rows else 0,
        "sentences": [
            {
                "id": s.id,
                "ord": s.ordinal,
                "zh": s.zh,
                "tr": s.trad,
                "t0": max(0, s.t0_ms + offsets.get(s.track_id, 0)),
                "t1": max(0, s.t1_ms + offsets.get(s.track_id, 0)),
                "en": s.en,
                "conf": s.align_conf,
                "anki": s.id in in_anki or None,
                "words": _slim_words(s.analysis, s.zh),
                "script_variants": script_variants(s.zh),
                "provenance": provenance(s),
            }
            for s in rows
        ],
    }


def _explain_response(
    session: Session, sentence_id: int, task, request_id=None, prefetch=False
) -> dict:
    from ..ai import provider
    from ..ai.tasks import ExplanationChanged, ExplanationRejected
    from ..ai.validation import InvalidExplanation
    from .ai import policy

    sentence = session.get(Sentence, sentence_id)
    if sentence is None:
        raise HTTPException(404)
    options = policy(session)
    if not options["enabled"] or (prefetch and not options["prefetch"]):
        raise HTTPException(409, "AI generation is disabled for this request in Settings")
    try:
        if not prefetch:
            provider.cancel_prefetches()
        with provider.request_scope(
            str(request_id) if request_id else None,
            priority="prefetch" if prefetch else "interactive",
        ):
            artifact = task(session, sentence)
    except ExplanationRejected as error:
        raise HTTPException(
            409,
            {
                "code": "artifact_rejected",
                "artifact_id": error.artifact_id,
                "message": "This explanation was rejected. Request another attempt explicitly.",
            },
        ) from error
    except ExplanationChanged as error:
        raise HTTPException(409, str(error)) from error
    except InvalidExplanation as error:
        raise HTTPException(422, str(error)) from error
    except provider.ProviderUnavailable as error:
        raise HTTPException(503, str(error)) from error
    except provider.ProviderBusy as error:
        raise HTTPException(429, str(error)) from error
    except provider.ProviderCancelled as error:
        raise HTTPException(409, "AI request cancelled") from error
    except provider.ProviderTimeout as error:
        raise HTTPException(504, str(error)) from error
    except provider.ProviderFailed as error:
        raise HTTPException(502, str(error)) from error
    return {
        **{key: value for key, value in artifact.output.items() if not key.startswith("_")},
        "artifact_id": artifact.id,
        "accepted": artifact.accepted,
        "prompt_version": artifact.prompt_version,
        "validation": "Structural and token checks only; language claims need review",
        "provider": artifact.provider,
        "model": artifact.model,
        "created_at": artifact.created_at,
    }


@router.post("/sentences/{sentence_id}/explain")
def explain(
    sentence_id: int,
    request_id: UUID | None = None,
    prefetch: bool = False,
    session: Session = Depends(get_session),
):
    from ..ai.tasks import explain_sentence

    return _explain_response(session, sentence_id, explain_sentence, request_id, prefetch)


@router.post("/sentences/{sentence_id}/explain-extras")
def explain_extras(
    sentence_id: int,
    request_id: UUID | None = None,
    prefetch: bool = False,
    session: Session = Depends(get_session),
):
    from ..ai.tasks import explain_sentence_extras

    return _explain_response(session, sentence_id, explain_sentence_extras, request_id, prefetch)


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
        "lexeme_id": lex.id,
        "simplified": lex.simplified,
        "traditional": lex.traditional,
        "pinyin": lex.pinyin,
        "hsk": lex.hsk_level,
        "is_dict": lex.is_dict,
        "pos": lex.pos,
        "freq_rank": lex.freq_rank,
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
    if body.start < 0 or body.end <= body.start or body.end > len(sentence.zh):
        raise HTTPException(400, "bad span")
    span = sentence.zh[body.start : body.end]
    if not span or len(span) > 12:
        raise HTTPException(400, "bad span")
    canonical = t2s(span)
    subs = {canonical[i:j] for i in range(len(canonical)) for j in range(i + 1, len(canonical) + 1)}
    lexes = session.scalars(select(Lexeme).where(Lexeme.simplified.in_(list(subs)))).all()
    lexes.sort(key=lambda lex: (lex.simplified != canonical, -len(lex.simplified)))
    return {
        "span": span,
        "candidates": [_lexeme_payload(session, lex) for lex in lexes[:10]],
    }


@router.get("/lexemes/{lexeme_id}")
def get_lexeme(lexeme_id: int, session: Session = Depends(get_session)):
    lex = session.get(Lexeme, lexeme_id)
    if lex is None:
        raise HTTPException(404)
    stats = session.get(LexemeStats, lexeme_id)
    payload = _lexeme_payload(session, lex)
    from ..evidence import lexeme_evidence

    payload["evidence"] = lexeme_evidence(session, lexeme_id)
    payload["stats"] = {
        "encounters": stats.encounters if stats else 0,
        "lookups": stats.lookups if stats else 0,
        "distinct_items": stats.distinct_items if stats else 0,
        "first_seen": stats.first_seen if stats else None,
        "last_seen": stats.last_seen if stats else None,
    }
    return payload
