"""Explicit note/deck/field mappings. Existing Anki templates are never modified."""

import hashlib
import json
from typing import Annotated

from pydantic import BaseModel, ConfigDict, Field, StringConstraints, model_validator

from ..models import Setting
from .connect import AnkiError, ac

Name = Annotated[
    str, StringConstraints(strict=True, strip_whitespace=True, min_length=1, max_length=200)
]
CANONICAL = (
    "ID",
    "Simplified",
    "Traditional",
    "Pinyin",
    "Meaning",
    "Sentence",
    "SentenceTraditional",
    "SentencePinyin",
    "SentenceMeaning",
    "Audio",
    "SentenceAudio",
    "Image",
)
DEFAULT_MAP = {key: key for key in CANONICAL if key != "Image"}


class Profile(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)
    deck: Name = "Mined::Immersion"
    model: Name = "Xiehanzi Mandarin"
    fields: dict[Name, Name] = Field(default_factory=lambda: dict(DEFAULT_MAP), max_length=12)
    templates_reviewed: bool = False
    word_tts: bool = False

    @model_validator(mode="after")
    def mapping(self):
        if set(self.fields) - set(CANONICAL):
            raise ValueError("Unknown source field")
        if "Meaning" not in self.fields or not {
            "Simplified",
            "Traditional",
            "Sentence",
            "SentenceTraditional",
        }.intersection(self.fields):
            raise ValueError("Map a Chinese text field and Meaning")
        if len(set(self.fields.values())) != len(self.fields):
            raise ValueError("Map each Anki field only once")
        return self


def current(session):
    row = session.get(Setting, "anki-export-profile")
    return Profile.model_validate(row.value if row else {})


def digest(value):
    return hashlib.sha256(
        json.dumps(value, ensure_ascii=False, sort_keys=True, default=str).encode()
    ).hexdigest()


def preflight(profile):
    version = ac("version")
    models = ac("modelNames")
    decks = ac("deckNames")
    if not isinstance(version, int) or not isinstance(models, list) or not isinstance(decks, list):
        raise AnkiError("AnkiConnect returned an invalid catalog")
    errors, warnings, fields = [], [], []
    if profile.model not in models:
        errors.append(
            "The configured note type does not exist. Select an existing note type in Settings."
        )
    else:
        fields = ac("modelFieldNames", modelName=profile.model)
        if not isinstance(fields, list) or not fields:
            raise AnkiError("The selected note type has no readable fields")
        missing = set(profile.fields.values()) - set(fields)
        if missing:
            errors.append("Mapped fields are missing: " + ", ".join(sorted(missing)))
        first_source = next(
            (key for key, target in profile.fields.items() if target == fields[0]), None
        )
        if first_source not in {
            "ID",
            "Simplified",
            "Traditional",
            "Sentence",
            "SentenceTraditional",
        }:
            errors.append(
                "Map the first Anki field to ID, Chinese text or Source sentence so it is nonblank."
            )
    if profile.deck not in decks:
        errors.append("The configured deck does not exist. Select an existing deck in Settings.")
    if not profile.templates_reviewed:
        errors.append(
            "Review the selected note type's card fronts/backs in Anki, then confirm them in Settings."
        )
    if not {"Sentence", "SentenceMeaning"} <= set(profile.fields):
        warnings.append(
            "This mapping omits some source context. Check that the resulting card matches your intended practice."
        )
    if "Pinyin" not in profile.fields:
        warnings.append(
            "Pinyin is not mapped; cards with a selected reading cannot be exported with this mapping."
        )
    if profile.word_tts:
        warnings.append(
            "Optional word TTS contacts an online service and is synthetic; source audio remains separate."
        )
    return {
        "ok": not errors,
        "errors": errors,
        "warnings": warnings,
        "models": models,
        "decks": decks,
        "model_fields": fields,
        "profile_hash": digest(profile.model_dump()),
    }


def chinese_key(profile):
    return next(
        key
        for key in ("Simplified", "Traditional", "Sentence", "SentenceTraditional")
        if key in profile.fields
    )
