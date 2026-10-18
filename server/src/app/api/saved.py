"""Saved words and sentences. Saving the same lexeme again appends a context
instead of duplicating (SAVE-002); contexts snapshot the sentence so they
survive re-ingestion."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import select, update
from sqlalchemy.orm import Session

from ..db import get_session
from ..models import (
    AnkiLink,
    Event,
    KnowledgeState,
    MediaItem,
    Lexeme,
    ReviewState,
    SavedContext,
    SavedItem,
    Sentence,
    SentenceIdentity,
    TokenOccurrence,
)

router = APIRouter()


class SaveIn(BaseModel):
    kind: str  # 'word' | 'sentence'
    lexeme_id: int | None = None
    surface: str | None = None
    sentence_id: int | None = None
    selected_reading: str | None = Field(default=None, max_length=160)
    selected_meaning: str | None = Field(default=None, max_length=1000)
    occurrence_start: int | None = Field(default=None, ge=0)


def _snapshot(session: Session, sentence: Sentence) -> dict:
    item = session.get(MediaItem, sentence.item_id)
    identity = session.get(SentenceIdentity, sentence.id)
    return {
        "item_id": sentence.item_id, "item_title": item.title if item else None,
        "sentence_ord": sentence.ordinal, "sentence_revision": identity.revision if identity else 0,
        "source_fingerprint": item.fingerprint if item else None,
        "zh": sentence.zh, "en": sentence.en, "t0_ms": sentence.t0_ms, "t1_ms": sentence.t1_ms,
        "analysis": sentence.analysis, "track_id": sentence.track_id,
    }


@router.post("/saved-items")
def save_item(body: SaveIn, session: Session = Depends(get_session)):
    if body.kind not in ("word", "sentence"):
        raise HTTPException(400, "kind must be word|sentence")
    sentence = session.get(Sentence, body.sentence_id) if body.sentence_id else None
    if body.sentence_id and sentence is None:
        raise HTTPException(404, "sentence not found")

    if body.kind == "word":
        if body.lexeme_id is None:
            raise HTTPException(400, "word saves need lexeme_id")
        if session.get(Lexeme, body.lexeme_id) is None:
            raise HTTPException(404, "lexeme not found")
        if body.selected_meaning is not None and not body.selected_meaning.strip():
            raise HTTPException(400, "meaning cannot be blank")
        if body.selected_reading is not None and not body.selected_reading.strip():
            raise HTTPException(400, "reading cannot be blank")
        if body.occurrence_start is not None:
            from .sentences import _slim_words
            originals = (sentence.analysis or {}).get("words", []) if sentence else []
            located = _slim_words(sentence.analysis, sentence.zh) if sentence else []
            # Reuse legacy offset recovery without persisting payload-trimmed glosses.
            words = [{**original, **{key: located_word[key] for key in ("start", "end") if key in located_word}}
                     for original, located_word in zip(originals, located)]
            if not any(w.get("start") == body.occurrence_start and w.get("lex") == body.lexeme_id for w in words):
                raise HTTPException(400, "occurrence does not match this word")
            if body.selected_reading:
                from ..lingua.readings import set_reading
                from ..corrections import identity_for
                from ..models import SentenceCorrection
                from copy import deepcopy
                identity = identity_for(session, sentence)
                try:
                    words = [set_reading(w, body.selected_reading)
                             if w.get("start") == body.occurrence_start and w.get("lex") == body.lexeme_id
                             else w for w in words]
                except ValueError as error:
                    raise HTTPException(400, str(error)) from error
                changed_analysis = {**(sentence.analysis or {}), "words": words}
                if changed_analysis != sentence.analysis:
                    identity.revision += 1
                    identity.overrides = {**(identity.overrides or {}), "analysis": deepcopy(changed_analysis)}
                    session.add(SentenceCorrection(sentence_id=sentence.id, revision=identity.revision,
                                                   action="select reading", overrides=deepcopy(identity.overrides)))
                sentence.analysis = changed_analysis
                session.execute(update(TokenOccurrence).where(
                    TokenOccurrence.sentence_id == sentence.id,
                    TokenOccurrence.start_offset == body.occurrence_start,
                ).values(reading=body.selected_reading))
                media = session.get(MediaItem, sentence.item_id)
                media.meta = {**(media.meta or {}), "analysis_rev": (media.meta or {}).get("analysis_rev", 0) + 1}
        item = session.scalar(
            select(SavedItem).where(
                SavedItem.kind == "word",
                SavedItem.lexeme_id == body.lexeme_id,
                SavedItem.selected_reading == body.selected_reading,
                SavedItem.selected_meaning == body.selected_meaning,
                SavedItem.archived.is_(False),
            )
        )
    else:
        if sentence is None:
            raise HTTPException(400, "sentence saves need sentence_id")
        item = session.scalar(
            select(SavedItem)
            .join(SavedContext)
            .where(
                SavedItem.kind == "sentence",
                SavedItem.archived.is_(False),
                SavedContext.sentence_id == sentence.id,
            )
        )

    created = item is None
    if created:
        item = SavedItem(
            kind=body.kind, lexeme_id=body.lexeme_id,
            selected_reading=body.selected_reading, selected_meaning=body.selected_meaning,
            selection_source="user" if body.selected_reading or body.selected_meaning else None,
            surface=body.surface or (sentence.zh if body.kind == "sentence" and sentence else None),
        )
        session.add(item)
        session.flush()

        # Saving is an explicit commitment to learn. Derived state remains
        # below manual and Anki evidence in the precedence order.
        if body.kind == "word" and body.lexeme_id is not None:
            ks = session.get(KnowledgeState, body.lexeme_id)
            if ks is None:
                session.add(KnowledgeState(
                    lexeme_id=body.lexeme_id, state="learning", source="derived"
                ))
            elif ks.source == "derived" and ks.state == "new":
                ks.state = "learning"

    if sentence is not None:
        dup = session.scalar(
            select(SavedContext).where(
                SavedContext.saved_item_id == item.id, SavedContext.sentence_id == sentence.id
            )
        )
        snapshot = {**_snapshot(session, sentence), "occurrence_start": body.occurrence_start,
                    "selected_reading": body.selected_reading, "selected_meaning": body.selected_meaning}
        occurrences = dict((dup.snapshot or {}).get("selected_occurrences", {})) if dup else {}
        if body.occurrence_start is not None and body.selected_reading:
            occurrences[str(body.occurrence_start)] = body.selected_reading
        snapshot["selected_occurrences"] = occurrences
        if dup is None:
            session.add(SavedContext(saved_item_id=item.id, sentence_id=sentence.id, snapshot=snapshot))
        elif body.selected_reading:
            from datetime import datetime, timezone
            dup.snapshot = snapshot
            dup.added_at = datetime.now(timezone.utc)

    session.commit()
    return {"id": item.id, "created": created}


@router.get("/saved-items")
def list_saved(
    kind: str | None = None, archived: bool = False, limit: int = 200,
    session: Session = Depends(get_session),
):
    q = select(SavedItem).where(SavedItem.archived.is_(archived)).order_by(SavedItem.created_at.desc())
    if kind:
        q = q.where(SavedItem.kind == kind)
    items = session.scalars(q.limit(limit)).all()
    ctxs: dict[int, list] = {}
    for c in session.scalars(
        select(SavedContext).where(SavedContext.saved_item_id.in_([i.id for i in items]))
    ):
        ctxs.setdefault(c.saved_item_id, []).append({
            "sentence_id": c.sentence_id, **(c.snapshot or {}), "added_at": c.added_at,
        })
    sentence_ids = {
        context["sentence_id"]
        for contexts in ctxs.values()
        for context in contexts
        if context["sentence_id"] is not None
    }
    latest_play_state: dict[int, str] = {}
    if sentence_ids:
        for event in session.scalars(
            select(Event)
            .where(
                Event.sentence_id.in_(sentence_ids),
                Event.type.in_(("sentence_played", "sentence_play_reset")),
            )
            .order_by(Event.id)
        ):
            latest_play_state[event.sentence_id] = event.type
    for contexts in ctxs.values():
        for context in contexts:
            context["played"] = latest_play_state.get(context["sentence_id"]) == "sentence_played"
    links = dict(session.execute(
        select(AnkiLink.saved_item_id, AnkiLink.note_id)
        .where(AnkiLink.saved_item_id.in_([i.id for i in items]))
    ).all())
    reviews = {
        review.saved_item_id: review
        for review in session.scalars(
            select(ReviewState).where(ReviewState.saved_item_id.in_([i.id for i in items]))
        )
    }
    return {
        "items": [
            {
                "id": i.id, "kind": i.kind, "lexeme_id": i.lexeme_id, "surface": i.surface,
                "note": i.note, "tags": i.tags, "created_at": i.created_at,
                "selected_reading": i.selected_reading, "selected_meaning": i.selected_meaning,
                "selection_source": i.selection_source,
                "contexts": ctxs.get(i.id, []),
                "anki_note_id": links.get(i.id),
                "review": ({
                    "rung": reviews[i.id].rung,
                    "passes": reviews[i.id].passes,
                    "fails": reviews[i.id].fails,
                    "graduated": reviews[i.id].graduated,
                } if i.id in reviews else None),
            }
            for i in items
        ]
    }


class SavedPatch(BaseModel):
    note: str | None = None
    tags: list[str] | None = None
    archived: bool | None = None


@router.patch("/saved-items/{item_id}")
def patch_saved(item_id: int, body: SavedPatch, session: Session = Depends(get_session)):
    item = session.get(SavedItem, item_id)
    if item is None:
        raise HTTPException(404)
    if body.note is not None:
        item.note = body.note
    if body.tags is not None:
        item.tags = body.tags
    if body.archived is not None:
        item.archived = body.archived
    session.commit()
    return {"ok": True}


@router.delete("/saved-items/{item_id}")
def delete_saved(item_id: int, session: Session = Depends(get_session)):
    item = session.get(SavedItem, item_id)
    if item is None:
        raise HTTPException(404)
    contexts = session.scalars(
        select(SavedContext).where(SavedContext.saved_item_id == item_id)
    ).all()
    sentence_id = next((context.sentence_id for context in contexts if context.sentence_id), None)
    for c in contexts:
        session.delete(c)

    review = session.get(ReviewState, item_id)
    if review is not None:
        session.delete(review)

    # Preserve the Anki export audit even though this item is leaving the local
    # learning queue. The note remains linked to its lexeme where possible.
    for link in session.scalars(select(AnkiLink).where(AnkiLink.saved_item_id == item_id)):
        link.saved_item_id = None

    if item.kind == "word" and item.lexeme_id is not None:
        other_save = session.scalar(
            select(SavedItem.id).where(
                SavedItem.id != item_id,
                SavedItem.kind == "word",
                SavedItem.lexeme_id == item.lexeme_id,
                SavedItem.archived.is_(False),
            )
        )
        ks = session.get(KnowledgeState, item.lexeme_id)
        if other_save is None and ks is not None and ks.source == "derived":
            session.delete(ks)

    session.add(Event(
        type="unsave",
        lexeme_id=item.lexeme_id,
        sentence_id=sentence_id,
        data={"saved_item_id": item.id, "kind": item.kind},
    ))
    session.delete(item)
    session.commit()
    return {"ok": True}


@router.delete("/saved-items/{item_id}/review")
def reset_saved_review(item_id: int, session: Session = Depends(get_session)):
    item = session.get(SavedItem, item_id)
    if item is None:
        raise HTTPException(404)
    review = session.get(ReviewState, item_id)
    previous = None
    if review is not None:
        previous = {
            "rung": review.rung,
            "passes": review.passes,
            "fails": review.fails,
            "streak": review.streak,
            "graduated": review.graduated,
        }
        session.delete(review)
    sentence_id = session.scalar(
        select(SavedContext.sentence_id).where(
            SavedContext.saved_item_id == item_id,
            SavedContext.sentence_id.is_not(None),
        ).limit(1)
    )
    session.add(Event(
        type="review_reset",
        lexeme_id=item.lexeme_id,
        sentence_id=sentence_id,
        data={"saved_item_id": item_id, "kind": item.kind, "previous": previous},
    ))
    session.commit()
    return {"saved_item_id": item_id, "reset": review is not None}


@router.delete("/sentences/{sentence_id}/played")
def reset_sentence_played(sentence_id: int, session: Session = Depends(get_session)):
    sentence = session.get(Sentence, sentence_id)
    if sentence is None:
        raise HTTPException(404, "sentence not found")
    session.add(Event(
        type="sentence_play_reset",
        item_id=sentence.item_id,
        sentence_id=sentence.id,
        data={"preserves_history": True},
    ))
    session.commit()
    return {"sentence_id": sentence_id, "played": False}
