"""Structural and token grounding checks, not linguistic certification."""

from typing import Annotated
import unicodedata

from pydantic import BaseModel, ConfigDict, Field, StringConstraints, ValidationError

Nonblank = Annotated[
    str,
    StringConstraints(strict=True, strip_whitespace=True, min_length=1, max_length=2000),
]
Short = Annotated[
    str,
    StringConstraints(strict=True, strip_whitespace=True, min_length=1, max_length=300),
]
OptionalText = Annotated[str, StringConstraints(strict=True, max_length=3000)]


class Strict(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)


class Breakdown(Strict):
    zh: Short
    role: Nonblank


class Particle(Strict):
    zh: Short
    note: Nonblank


class Core(Strict):
    natural: Nonblank
    literal: Nonblank
    structure: Nonblank
    words: list[Breakdown] = Field(min_length=1, max_length=150)
    particles: list[Particle] = Field(max_length=40)


class Variation(Strict):
    zh: Nonblank
    note: Nonblank


class Example(Strict):
    zh: Nonblank
    en: Nonblank


class Pattern(Strict):
    name: Short
    examples: list[Example] = Field(max_length=2)


class Extras(Strict):
    pronunciation: list[Nonblank] = Field(max_length=8)
    nuance: OptionalText
    variations: list[Variation] = Field(max_length=2)
    pattern: Pattern | None
    mistakes: list[Nonblank] = Field(max_length=3)


class InvalidExplanation(RuntimeError):
    pass


def visible(text):
    return "".join(
        character
        for character in text
        if not character.isspace() and not unicodedata.category(character).startswith("P")
    )


def validate_result(kind, result, zh_tokens):
    try:
        parsed = (Core if kind == "explanation" else Extras).model_validate(result)
    except ValidationError as error:
        # Error codes/paths are useful diagnostics without exposing raw provider output.
        codes = ", ".join(
            ".".join(map(str, entry["loc"])) + ":" + entry["type"]
            for entry in error.errors(include_input=False)[:6]
        )
        raise InvalidExplanation(f"Invalid explanation structure ({codes})") from error
    data = parsed.model_dump()
    if kind == "explanation":
        source = [word["t"] for word in zh_tokens if word.get("t")]
        if not source:
            raise InvalidExplanation("No indexed source tokens to ground the explanation")
        cursor = 0
        for chunk in data["words"]:
            text, combined = chunk["zh"], ""
            while cursor < len(source) and len(combined) < len(text):
                combined += source[cursor]
                cursor += 1
            if combined != text:
                raise InvalidExplanation("Word breakdown must use adjacent source tokens in order")
        if cursor != len(source):
            raise InvalidExplanation("Word breakdown must cover every source token once")
        sentence = "".join(source)
        if any(particle["zh"] not in sentence for particle in data["particles"]):
            raise InvalidExplanation("Particle notes must refer to text present in the source")
        if len({particle["zh"] for particle in data["particles"]}) != len(data["particles"]):
            raise InvalidExplanation("Duplicate particle entries")
    else:
        if any(
            not visible(entry["zh"])
            for entry in data["variations"]
            + (data["pattern"]["examples"] if data["pattern"] else [])
        ):
            raise InvalidExplanation("Examples need readable source-language text")
    return data


def validate_translations(result, count):
    if (
        not isinstance(result, list)
        or len(result) != count
        or any(
            not isinstance(value, str) or not value.strip() or len(value) > 10000
            for value in result
        )
    ):
        raise InvalidExplanation(
            "Translation response must contain one nonblank string per sentence"
        )
    return [value.strip() for value in result]
