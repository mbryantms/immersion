"""Revision-checked, append-only local transcript corrections."""

from copy import deepcopy
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import select, update
from sqlalchemy.orm import Session

from ..db import get_session
from ..models import MediaItem, Sentence, SentenceCorrection, SentenceIdentity
from ..corrections import (
    identity_for,
    apply_overrides,
    bump_revision,
    corrected_analysis,
    reindex_sentence,
)

router = APIRouter()


class WordEdit(BaseModel):
    start: int = Field(ge=0)
    reading: str | None = Field(default=None, max_length=160)
    meaning: str | None = Field(default=None, max_length=1000)


class CorrectionIn(BaseModel):
    expected_revision: int = Field(ge=0)
    zh: str | None = Field(default=None, min_length=1, max_length=2000)
    en: str | None = Field(default=None, max_length=4000)
    t0_ms: int | None = Field(default=None, ge=0)
    t1_ms: int | None = Field(default=None, ge=0)
    words: list[WordEdit] = Field(default_factory=list, max_length=300)
    reset: bool = False
    restore_revision: int | None = Field(default=None, ge=1)


def _detail(session: Session, sentence: Sentence, identity: SentenceIdentity):
    from .sentences import _slim_words

    history = session.execute(
        select(
            SentenceCorrection.revision, SentenceCorrection.action, SentenceCorrection.created_at
        )
        .where(SentenceCorrection.sentence_id == sentence.id)
        .order_by(SentenceCorrection.revision.desc())
        .limit(50)
    ).all()
    return {
        "sentence_id": sentence.id,
        "revision": identity.revision,
        "source": identity.source,
        "overrides": identity.overrides or {},
        "current": {
            "zh": sentence.zh,
            "en": sentence.en,
            "t0_ms": sentence.t0_ms,
            "t1_ms": sentence.t1_ms,
            "words": _slim_words(sentence.analysis, sentence.zh),
        },
        "history": [
            {"revision": row.revision, "action": row.action, "created_at": row.created_at}
            for row in history
        ],
    }


@router.get("/sentences/{sentence_id}/corrections")
def get_corrections(sentence_id: int, session: Session = Depends(get_session)):
    sentence = session.get(Sentence, sentence_id)
    if sentence is None:
        raise HTTPException(404, "sentence no longer present; saved snapshots remain available")
    identity = identity_for(session, sentence)
    session.commit()
    return _detail(session, sentence, identity)


@router.patch("/sentences/{sentence_id}/corrections")
def patch_correction(sentence_id: int, body: CorrectionIn, session: Session = Depends(get_session)):
    sentence = session.get(Sentence, sentence_id)
    if sentence is None:
        raise HTTPException(404, "sentence no longer present")
    identity = identity_for(session, sentence)
    changed_fields = body.model_fields_set - {"expected_revision", "reset", "restore_revision"}
    if (body.reset and body.restore_revision) or (
        (body.reset or body.restore_revision) and changed_fields
    ):
        raise HTTPException(400, "reset/restore cannot be combined with edits")
    claimed = session.execute(
        update(SentenceIdentity)
        .where(
            SentenceIdentity.id == sentence_id,
            SentenceIdentity.revision == body.expected_revision,
        )
        .values(revision=body.expected_revision + 1)
        .execution_options(synchronize_session=False)
    )
    if claimed.rowcount != 1:
        session.rollback()
        raise HTTPException(
            409, "This line changed. Reload its history before saving your correction."
        )
    if body.reset:
        overrides, action = {}, "reset"
    elif body.restore_revision:
        previous = session.scalar(
            select(SentenceCorrection).where(
                SentenceCorrection.sentence_id == sentence_id,
                SentenceCorrection.revision == body.restore_revision,
            )
        )
        if previous is None:
            session.rollback()
            raise HTTPException(404, "correction revision not found")
        overrides, action = deepcopy(previous.overrides), "restore"
    else:
        overrides, action = deepcopy(identity.overrides or {}), "edit"
        for field in ("zh", "en", "t0_ms", "t1_ms"):
            if field in body.model_fields_set:
                value = getattr(body, field)
                if field != "en" and value is None:
                    session.rollback()
                    raise HTTPException(400, f"{field} cannot be null")
                if field == "zh" and not value.strip():
                    session.rollback()
                    raise HTTPException(400, "Chinese text cannot be blank")
                overrides[field] = value
        zh = overrides.get("zh", identity.source["zh"])
        try:
            if zh != sentence.zh:
                if "en" not in body.model_fields_set:
                    overrides["en"] = None
                if body.words:
                    raise ValueError("Save text first, then edit the new word positions")
                overrides["analysis"] = corrected_analysis(session, zh)
            elif body.words:
                from ..lingua.readings import set_reading

                from .sentences import _slim_words

                analysis = deepcopy(sentence.analysis or {"words": []})
                positioned = _slim_words(sentence.analysis, sentence.zh)
                analysis["words"] = [
                    {**word, **{key: located[key] for key in ("start", "end") if key in located}}
                    for word, located in zip(analysis["words"], positioned)
                ]
                for edit in body.words:
                    word = next(
                        (
                            w
                            for w in analysis["words"]
                            if w.get("start") == edit.start and w["type"] == "zh"
                        ),
                        None,
                    )
                    if word is None:
                        raise ValueError("Word position no longer exists; reload this line")
                    if edit.reading is not None and not edit.reading.strip():
                        raise ValueError(
                            "Enter numbered pinyin, or reset the line to its source reading"
                        )
                    if edit.reading:
                        word.update(set_reading(word, edit.reading))
                    if edit.meaning is not None:
                        if edit.meaning.strip():
                            word["meaning"] = edit.meaning
                            word["gloss"] = [{"py": word.get("reading"), "defs": [edit.meaning]}]
                        else:
                            from ..lingua.cedict import load

                            word.pop("meaning", None)
                            word["gloss"] = load().gloss(word.get("canonical", word["t"]))
                overrides["analysis"] = analysis
        except ValueError as error:
            session.rollback()
            raise HTTPException(400, str(error)) from error
    t0, t1 = (overrides.get(key, identity.source[key]) for key in ("t0_ms", "t1_ms"))
    if ("t0_ms" in overrides or "t1_ms" in overrides) and t1 <= t0:
        session.rollback()
        raise HTTPException(400, "End time must be after start time")
    for key in ("zh", "en", "en_source", "t0_ms", "t1_ms", "analysis", "align_conf"):
        if key in identity.source:
            setattr(sentence, key, deepcopy(identity.source[key]))
    identity.revision = body.expected_revision + 1
    identity.overrides = overrides
    apply_overrides(sentence, identity)
    reindex_sentence(session, sentence)
    bump_revision(session.get(MediaItem, sentence.item_id))
    session.add(
        SentenceCorrection(
            sentence_id=sentence.id,
            revision=identity.revision,
            action=action,
            overrides=deepcopy(overrides),
        )
    )
    session.commit()
    return _detail(session, sentence, identity)
