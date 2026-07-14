"""AI jobs. translate_item fills sentence.en per batch of 25 with a commit
after every batch — a crashed or failed job resumes from the first untranslated
sentence instead of redoing the episode (podreader was all-or-nothing)."""

from __future__ import annotations

import hashlib

from sqlalchemy import select
from sqlalchemy.orm import Session

from ..config import settings
from ..models import AiArtifact, MediaItem, Sentence
from . import provider

BATCH = 25
PROMPT_VERSION = "1"
PROMPT = """Translate these Mandarin Chinese sentences to English.
Keep translations concise and fairly literal so learners can map words across.
Keep proper nouns as-is. Return ONLY a JSON array of strings, one per input
sentence, same order, no commentary.

{numbered}"""


EXPLAIN_PROMPT_VERSION = "1"
EXPLAIN_PROMPT = """You are helping an intermediate Mandarin learner understand one sentence
from something they are watching. Be concise and concrete; no praise, no filler.

Sentence: {zh}
{en_line}
Return ONLY JSON with this shape:
{{"gist": "one-line natural reading of the whole sentence",
  "chunks": [{{"zh": "chunk of the sentence", "note": "role/meaning in this sentence"}}],
  "points": ["short grammar/usage/nuance notes worth remembering, if any"]}}

Chunks must cover the sentence in order (3-6 chunks). Keep every note under
~15 words. Mention colloquialisms, idioms, or register only when present."""


def explain_sentence(session: Session, sentence: Sentence) -> AiArtifact:
    """Cached AI explanation of one sentence; the cache key is the zh text, so
    re-ingested episodes reuse explanations for unchanged sentences."""
    input_hash = hashlib.sha256(sentence.zh.encode()).hexdigest()[:16]
    cached = session.scalar(
        select(AiArtifact).where(
            AiArtifact.target_kind == "sentence",
            AiArtifact.artifact_type == "explanation",
            AiArtifact.input_hash == input_hash,
            AiArtifact.prompt_version == EXPLAIN_PROMPT_VERSION,
        )
    )
    if cached is not None:
        return cached

    en_line = f"Track translation (context, may be loose): {sentence.en}\n" if sentence.en else ""
    result = provider.complete_json(
        EXPLAIN_PROMPT.format(zh=sentence.zh, en_line=en_line), timeout_s=120
    )
    if not isinstance(result, dict) or "gist" not in result:
        raise RuntimeError(f"malformed explanation payload: {str(result)[:200]}")
    artifact = AiArtifact(
        target_kind="sentence", target_id=sentence.id, artifact_type="explanation",
        provider="claude-cli", model=settings.ai_model,
        prompt_version=EXPLAIN_PROMPT_VERSION, input_hash=input_hash,
        output=result,
    )
    session.add(artifact)
    session.commit()
    return artifact


def translate_item(session: Session, item_id: int, progress=lambda msg: None) -> dict:
    item = session.get(MediaItem, item_id)
    if item is None:
        return {"skipped": True}
    if not provider.available():
        return {"skipped": "claude CLI not available; sentences stay untranslated"}

    todo = session.scalars(
        select(Sentence)
        .where(Sentence.item_id == item_id, Sentence.en.is_(None))
        .order_by(Sentence.ordinal)
    ).all()
    done = 0
    for i in range(0, len(todo), BATCH):
        chunk = todo[i : i + BATCH]
        progress(f"translating {i + len(chunk)}/{len(todo)}")
        numbered = "\n".join(f"{j + 1}. {s.zh}" for j, s in enumerate(chunk))
        result = provider.complete_json(PROMPT.format(numbered=numbered))
        if not isinstance(result, list) or len(result) != len(chunk):
            raise RuntimeError(
                f"translation count mismatch: {len(chunk)} sent, "
                f"{len(result) if isinstance(result, list) else type(result)} back"
            )
        for s, en in zip(chunk, result):
            s.en = str(en)
            s.en_source = "ai"
            session.add(AiArtifact(
                target_kind="sentence", target_id=s.id, artifact_type="translation",
                provider="claude-cli", model=settings.ai_model,
                prompt_version=PROMPT_VERSION,
                input_hash=hashlib.sha256(s.zh.encode()).hexdigest()[:16],
                output={"en": s.en},
            ))
        session.commit()  # per-batch checkpoint: retries resume where en is NULL
        done += len(chunk)
    return {"translated": done, "already_done": len(todo) == 0}
