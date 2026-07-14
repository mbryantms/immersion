"""Saved words and sentences. Saving the same lexeme again appends a context
instead of duplicating (SAVE-002); contexts snapshot the sentence so they
survive re-ingestion."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..db import get_session
from ..models import (
    AnkiLink,
    Event,
    KnowledgeState,
    MediaItem,
    ReviewState,
    SavedContext,
    SavedItem,
    Sentence,
)

router = APIRouter()


class SaveIn(BaseModel):
    kind: str  # 'word' | 'sentence'
    lexeme_id: int | None = None
    surface: str | None = None
    sentence_id: int | None = None


def _snapshot(session: Session, sentence: Sentence) -> dict:
    item = session.get(MediaItem, sentence.item_id)
    return {
        "item_id": sentence.item_id, "item_title": item.title if item else None,
        "sentence_ord": sentence.ordinal,
        "zh": sentence.zh, "en": sentence.en, "t0_ms": sentence.t0_ms, "t1_ms": sentence.t1_ms,
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
        item = session.scalar(
            select(SavedItem).where(
                SavedItem.kind == "word",
                SavedItem.lexeme_id == body.lexeme_id,
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
        if dup is None:
            session.add(SavedContext(
                saved_item_id=item.id, sentence_id=sentence.id, snapshot=_snapshot(session, sentence)
            ))
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
