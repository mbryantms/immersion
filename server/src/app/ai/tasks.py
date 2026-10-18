"""AI jobs. translate_item fills sentence.en per batch of 25 with a commit
after every batch — a crashed or failed job resumes from the first untranslated
sentence instead of redoing the episode (podreader was all-or-nothing)."""

from __future__ import annotations

import hashlib
import json
import threading
import weakref
from contextlib import contextmanager

from sqlalchemy import select
from sqlalchemy.orm import Session

from ..config import settings
from ..models import AiArtifact, Event, MediaItem, Sentence, Setting
from .validation import InvalidExplanation, validate_result, validate_translations
from . import provider

BATCH = 25
PROMPT_VERSION = "1"
PROMPT = """Translate these Mandarin Chinese sentences to English.
Keep translations concise and fairly literal so learners can map words across.
Keep proper nouns as-is. Return ONLY a JSON array of strings, one per input
sentence, same order, no commentary.

{numbered}"""


EXPLAIN_PROMPT_VERSION = "4"
# Core and extras are separate, validated artifacts. The UI explicitly requests
# core before extras; cancelled work cannot chain speculative generations.
EXPLAIN_CORE_PROMPT = """You are helping an intermediate Mandarin learner deeply understand ONE
sentence from something they are watching. Be concrete and concise; no praise,
no filler. Facts they can see (pinyin, HSK levels, dictionary glosses) are
supplied by the app — your job is the interpretive layer.

Sentence: {zh}
Tokenized as: {tokens}
{en_line}
Return ONLY JSON with this shape:
{{"natural": "natural English translation",
  "literal": "word-for-word gloss preserving Chinese order, e.g. 'he use hand twist-tight [done] loose parts'",
  "structure": "1-3 sentences: why the sentence is ordered/built this way",
  "words": [{{"zh": "token or adjacent-token group", "role": "grammatical role + in-context meaning, <=12 words"}}],
  "particles": [{{"zh": "了/着/过/吧/呢/来/给/的/得/地/把/被...", "note": "why THIS particle here, what changes without it, <=18 words"}}]}}

Rules: words[] must cover the sentence in order using ONLY the given tokens
(adjacent tokens may be grouped; skip punctuation). particles[] covers every
function word present ([] if none). Keep it tight."""

EXPLAIN_EXTRAS_PROMPT = """You are helping an intermediate Mandarin learner go deeper on ONE sentence
from something they are watching. Be concrete and concise; no filler.

Sentence: {zh}
Tokenized as: {tokens}
{en_line}
Return ONLY JSON with this shape (use "" / [] when not applicable):
{{"pronunciation": ["tone sandhi / erhua / neutral-tone reductions / connected-speech notes that apply HERE; [] if none"],
  "nuance": "cultural or contextual nuance; \\"\\" if none",
  "variations": [{{"zh": "same meaning, different register or region", "note": "e.g. more formal / casual / Taiwan usage"}}],
  "pattern": {{"name": "the sentence's key grammar pattern", "examples": [{{"zh": "new example sentence using the pattern", "en": "its translation"}}]}},
  "mistakes": ["common learner mistakes with this pattern, <=18 words each"]}}

Rules: variations and pattern.examples max 2 each; mistakes max 3. Keep it tight."""


def _sentence_pinyin(words: list[dict]) -> str:
    """Display pinyin from the stored analysis: word-spaced, punctuation glued."""
    parts: list[str] = []
    for w in words:
        if w.get("type") == "zh":
            parts.append("".join(w.get("py", [])) or w["t"])
        elif w["t"].strip():
            if parts:
                parts[-1] += w["t"]
            else:
                parts.append(w["t"])
    return " ".join(parts)


def _tts_pinyin(text: str) -> str:
    """Tone-marked pinyin for AI-generated example text (deterministic)."""
    from pypinyin import Style, pinyin as py

    return " ".join(s[0] for s in py(text, style=Style.TONE))


def _merge_breakdown(ai_words: list[dict], zh_tokens: list[dict], lex_by_id: dict) -> list[dict]:
    """Attach app-known facts (pinyin, HSK, POS, glosses) to the AI's role
    chunks by walking the sentence tokens the chunks were built from."""
    out: list[dict] = []
    i = 0
    for chunk in ai_words:
        text = (chunk.get("zh") or "").strip()
        if not text:
            continue
        toks, acc, j = [], "", i
        while j < len(zh_tokens) and len(acc) < len(text):
            acc += zh_tokens[j]["t"]
            toks.append(zh_tokens[j])
            j += 1
        if acc == text:
            i = j
        else:
            raise InvalidExplanation("Breakdown drifted from adjacent source tokens")
        entry: dict = {"zh": text, "role": chunk.get("role") or chunk.get("note") or ""}
        if toks:
            entry["py"] = " ".join("".join(t.get("py", [])) for t in toks)
            levels = [
                lex_by_id[t["lex"]].hsk_level
                for t in toks
                if t.get("lex") in lex_by_id and lex_by_id[t["lex"]].hsk_level
            ]
            if levels:
                entry["hsk"] = max(levels)
            if len(toks) == 1:
                lex = lex_by_id.get(toks[0].get("lex"))
                if lex is not None and lex.pos:
                    entry["pos"] = lex.pos
                gloss = toks[0].get("gloss")
                if gloss:
                    entry["defs"] = (gloss[0].get("defs") or [])[:2]
        out.append(entry)
    return out


class ExplanationRejected(RuntimeError):
    def __init__(self, artifact_id):
        self.artifact_id = artifact_id
        super().__init__("Explanation was rejected")


class ExplanationChanged(RuntimeError):
    pass


_inflight = weakref.WeakValueDictionary()
_inflight_guard = threading.Lock()


@contextmanager
def _flight_lock(key):
    with _inflight_guard:
        lock = _inflight.get(key)
        if lock is None:
            lock = threading.Lock()
            _inflight[key] = lock
    while not lock.acquire(timeout=0.1):
        provider.check_cancelled()
    try:
        provider.check_cancelled()
        yield
    finally:
        lock.release()


def explanation_context(sentence):
    context = {
        "zh": sentence.zh,
        "en": sentence.en,
        "analysis": sentence.analysis,
        "model": settings.ai_model,
        "prompt_version": EXPLAIN_PROMPT_VERSION,
    }
    return hashlib.sha256(
        json.dumps(context, ensure_ascii=False, sort_keys=True).encode()
    ).hexdigest()


def retry_key(kind, context_hash):
    return f"ai-generation:{kind}:{context_hash}"


def generation_state(session, kind, context_hash):
    row = session.get(Setting, retry_key(kind, context_hash))
    return int((row.value or {}).get("generation", 0)) if row else 0


def _explain_context(session: Session, sentence: Sentence):
    from ..models import Lexeme

    words = (sentence.analysis or {}).get("words", [])
    zh_tokens = [w for w in words if w.get("type") == "zh"]
    lex_ids = [w["lex"] for w in zh_tokens if w.get("lex")]
    lex_by_id = (
        {lex.id: lex for lex in session.scalars(select(Lexeme).where(Lexeme.id.in_(lex_ids)))}
        if lex_ids
        else {}
    )
    return words, zh_tokens, lex_by_id


def _cached_artifact(session, artifact_type, input_hash):
    return session.scalar(
        select(AiArtifact)
        .where(
            AiArtifact.target_kind == "sentence",
            AiArtifact.artifact_type == artifact_type,
            AiArtifact.input_hash == input_hash,
            AiArtifact.prompt_version == EXPLAIN_PROMPT_VERSION,
        )
        .order_by(AiArtifact.id)
        .limit(1)
    )


def _explain(
    session: Session,
    sentence: Sentence,
    artifact_type: str,
    prompt: str,
    required_key: str,
) -> AiArtifact:
    context_hash = explanation_context(sentence)
    generation = generation_state(session, artifact_type, context_hash)
    input_hash = hashlib.sha256(f"{context_hash}:{generation}".encode()).hexdigest()

    def cached():
        artifact = _cached_artifact(session, artifact_type, input_hash)
        if artifact is not None and artifact.accepted is False:
            raise ExplanationRejected(artifact.id)
        return artifact

    existing = cached()
    if existing is not None:
        return existing
    with _flight_lock(f"{artifact_type}:{input_hash}"):
        existing = cached()
        if existing is not None:
            return existing
        if not provider.available():
            raise provider.ProviderUnavailable("Optional AI provider is unavailable")
        words, zh_tokens, lex_by_id = _explain_context(session, sentence)
        en_line = (
            f"{sentence.en_source or 'Unknown source'} translation (may be loose): {sentence.en}\n"
            if sentence.en
            else ""
        )
        result = provider.complete_json(
            prompt.format(
                zh=sentence.zh,
                tokens=" | ".join(word["t"] for word in zh_tokens) or sentence.zh,
                en_line=en_line,
            ),
            timeout_s=180,
        )
        provider.check_cancelled()
        # Refresh after the long provider call. A concurrent local correction must
        # win; never publish an explanation generated for an older source revision.
        session.refresh(sentence)
        if explanation_context(sentence) != context_hash:
            session.add(
                Event(
                    type="ai_output_discarded",
                    sentence_id=sentence.id,
                    data={
                        "reason": "source_changed",
                        "context_hash": context_hash,
                        "artifact_type": artifact_type,
                    },
                )
            )
            session.commit()
            raise ExplanationChanged(
                "The source changed while AI was running. Reload before trying again"
            )
        try:
            result = validate_result(artifact_type, result, zh_tokens)
        except InvalidExplanation as error:
            # Do not cache malformed output as a usable explanation or expose it.
            session.add(
                Event(
                    type="ai_output_rejected",
                    sentence_id=sentence.id,
                    data={
                        "reason": str(error),
                        "context_hash": context_hash,
                        "artifact_type": artifact_type,
                    },
                )
            )
            session.commit()
            raise
        if artifact_type == "explanation":
            result["words"] = _merge_breakdown(result["words"], zh_tokens, lex_by_id)
            result["pinyin"] = _sentence_pinyin(words)
            levels = [lex.hsk_level for lex in lex_by_id.values() if lex.hsk_level]
            result["hsk"] = {
                "level": max(levels) if levels else None,
                "offlist": [
                    lex.simplified
                    for lex in lex_by_id.values()
                    if lex.hsk_level is None and lex.is_dict
                ],
            }
        else:
            for example in (result.get("pattern") or {}).get("examples", []):
                example["py"] = _tts_pinyin(example["zh"])
            for variation in result["variations"]:
                variation["py"] = _tts_pinyin(variation["zh"])
        result["_context_hash"] = context_hash
        result["_generation"] = generation
        artifact = AiArtifact(
            target_kind="sentence",
            target_id=sentence.id,
            artifact_type=artifact_type,
            provider="claude-cli",
            model=settings.ai_model,
            prompt_version=EXPLAIN_PROMPT_VERSION,
            input_hash=input_hash,
            output=result,
        )
        session.add(artifact)
        session.commit()
        return artifact


def explain_sentence(session: Session, sentence: Sentence) -> AiArtifact:
    return _explain(session, sentence, "explanation", EXPLAIN_CORE_PROMPT, "natural")


def explain_sentence_extras(session: Session, sentence: Sentence) -> AiArtifact:
    return _explain(session, sentence, "explanation_extras", EXPLAIN_EXTRAS_PROMPT, "pattern")


def translate_item(session: Session, item_id: int, progress=lambda msg: None) -> dict:
    item = session.get(MediaItem, item_id)
    if item is None:
        return {"skipped": True}
    policy_row = session.get(Setting, "ai-policy")
    if policy_row and not (policy_row.value or {}).get("enabled", True):
        return {"skipped": "AI generation disabled"}
    if not provider.available():
        return {"skipped": "claude CLI not available; sentences stay untranslated"}

    todo = session.scalars(
        select(Sentence)
        .where(
            Sentence.item_id == item_id,
            Sentence.en.is_(None),
            Sentence.en_source.is_(None) | (Sentence.en_source != "user"),
        )
        .order_by(Sentence.ordinal)
    ).all()
    done = 0
    for i in range(0, len(todo), BATCH):
        chunk = todo[i : i + BATCH]
        progress(f"translating {i + len(chunk)}/{len(todo)}")
        numbered = "\n".join(f"{j + 1}. {s.zh}" for j, s in enumerate(chunk))
        from ..models import SentenceIdentity

        expected = dict(
            session.execute(
                select(SentenceIdentity.id, SentenceIdentity.revision).where(
                    SentenceIdentity.id.in_([sentence.id for sentence in chunk])
                )
            ).all()
        )
        session.expire_all()
        policy_row = session.get(Setting, "ai-policy")
        if policy_row and not (policy_row.value or {}).get("enabled", True):
            break
        with provider.request_scope(priority="background"):
            result = provider.complete_json(PROMPT.format(numbered=numbered))
        result = validate_translations(result, len(chunk))
        translated = 0
        for s, en in zip(chunk, result):
            from ..corrections import identity_for
            from sqlalchemy import update

            identity = identity_for(session, s)
            revision = expected.get(s.id, 0)
            claimed = session.execute(
                update(SentenceIdentity)
                .where(SentenceIdentity.id == s.id, SentenceIdentity.revision == revision)
                .values(revision=revision + 1)
                .execution_options(synchronize_session=False)
            )
            if claimed.rowcount != 1:
                session.expire(s)
                continue  # A local edit made while the provider was running wins.
            s.en = str(en)
            s.en_source = "ai"
            identity.source = {**identity.source, "en": s.en, "en_source": "ai"}
            identity.revision = revision + 1
            translated += 1
            session.add(
                AiArtifact(
                    target_kind="sentence",
                    target_id=s.id,
                    artifact_type="translation",
                    provider="claude-cli",
                    model=settings.ai_model,
                    prompt_version=PROMPT_VERSION,
                    input_hash=hashlib.sha256(s.zh.encode()).hexdigest()[:16],
                    output={"en": s.en},
                )
            )
        from sqlalchemy import text

        for s in chunk:
            session.execute(
                text("UPDATE sentence_fts SET en = :en WHERE rowid = :id"),
                {"en": s.en, "id": s.id},
            )
        session.refresh(item, attribute_names=["meta"])
        item.meta = {
            **(item.meta or {}),
            "analysis_rev": (item.meta or {}).get("analysis_rev", 0) + 1,
        }
        session.commit()  # per-batch checkpoint: retries resume where en is NULL
        done += translated
    return {"translated": done, "already_done": len(todo) == 0}
