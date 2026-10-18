"""Source snapshots, stable identity, and local correction projections."""

from __future__ import annotations

from copy import deepcopy
from sqlalchemy import func, select, delete, text
from sqlalchemy.orm import Session
from .models import Event, MediaItem, Sentence, SentenceIdentity, TokenOccurrence


def bump_revision(item: MediaItem) -> None:
    item.meta = {**(item.meta or {}), "analysis_rev": (item.meta or {}).get("analysis_rev", 0) + 1}


def source_snapshot(sentence: Sentence, fingerprint=None) -> dict:
    return {
        key: deepcopy(getattr(sentence, key))
        for key in ("zh", "en", "en_source", "t0_ms", "t1_ms", "ordinal", "align_conf", "analysis")
    } | {"fingerprint": fingerprint}


def identity_for(session: Session, sentence: Sentence) -> SentenceIdentity:
    identity = session.get(SentenceIdentity, sentence.id)
    if identity is None:
        item = session.get(MediaItem, sentence.item_id)
        identity = SentenceIdentity(
            id=sentence.id,
            item_id=sentence.item_id,
            track_id=sentence.track_id,
            source=source_snapshot(sentence, item.fingerprint if item else None),
        )
        session.add(identity)
        session.flush()
    return identity


def reserve_ids(session: Session) -> None:
    # Legacy imports/tests can contain event IDs larger than any current row.
    high = max(
        session.scalar(select(func.max(Sentence.id))) or 0,
        session.scalar(select(func.max(Event.sentence_id))) or 0,
    )
    if high and session.get(SentenceIdentity, high) is None:
        session.add(SentenceIdentity(id=high, source={}))
        session.flush()


def apply_overrides(sentence: Sentence, identity: SentenceIdentity) -> None:
    overrides = identity.overrides or {}
    for key in ("zh", "en", "t0_ms", "t1_ms", "analysis"):
        if key in overrides:
            setattr(sentence, key, deepcopy(overrides[key]))
    if "en" in overrides:
        sentence.en_source = "user"
    from .lingua.convert import s2t

    traditional = s2t(sentence.zh)
    sentence.trad = traditional if traditional != sentence.zh else None


def reindex_sentence(session: Session, sentence: Sentence) -> None:
    from .ingest.analysis import token_occurrences, write_fts

    session.execute(delete(TokenOccurrence).where(TokenOccurrence.sentence_id == sentence.id))
    session.add_all(token_occurrences(sentence.item_id, [sentence]))
    session.execute(text("DELETE FROM sentence_fts WHERE rowid=:id"), {"id": sentence.id})
    write_fts(session, [sentence])


def corrected_analysis(session: Session, zh: str) -> dict:
    """Immediate local dictionary segmentation; no Torch/model/remote dependency."""
    from .lingua.cedict import load
    from .lingua.pipeline import analyze_sentences, CJK
    from .ingest.analysis import get_or_create_lexemes, link_words
    from .lingua.convert import t2s

    dictionary = load()
    normalized = t2s(zh)
    if len(normalized) != len(zh):
        normalized = zh
    tokens, cursor = [], 0
    while cursor < len(normalized):
        token = (
            dictionary.longest_match(normalized, cursor) if CJK.match(normalized[cursor]) else None
        )
        token = token or normalized[cursor]
        tokens.append(token)
        cursor += len(token)
    words = analyze_sentences([zh], dictionary, token_lists=[tokens])[0]
    ids = get_or_create_lexemes(session, {w["t"] for w in words if w["type"] == "zh"})
    link_words(zh, words, ids)
    return {"words": words}
