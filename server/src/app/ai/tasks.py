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
