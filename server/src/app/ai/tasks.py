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


EXPLAIN_PROMPT_VERSION = "2"
EXPLAIN_PROMPT = """You are helping an intermediate Mandarin learner deeply understand ONE
sentence from something they are watching. Be concrete and concise; no praise,
no filler. Facts they can see (pinyin, HSK levels, dictionary glosses) are
supplied by the app — your job is the interpretive layer.

Sentence: {zh}
Tokenized as: {tokens}
{en_line}
Return ONLY JSON with this shape (omit nothing; use "" / [] when not applicable):
{{"natural": "natural English translation",
  "literal": "word-for-word gloss preserving Chinese order, e.g. 'he use hand twist-tight [done] loose parts'",
  "structure": "1-3 sentences: why the sentence is ordered/built this way",
  "words": [{{"zh": "token or adjacent-token group", "role": "grammatical role + in-context meaning, <=15 words"}}],
  "particles": [{{"zh": "了/着/过/吧/呢/来/给/的/得/地/把/被...", "note": "why THIS particle here, what changes without it, <=20 words"}}],
  "pronunciation": ["tone sandhi / erhua / neutral-tone reductions / connected-speech notes that apply HERE; [] if none"],
  "nuance": "cultural or contextual nuance; \\"\\" if none",
  "variations": [{{"zh": "same meaning, different register or region", "note": "e.g. more formal / casual / Taiwan usage"}}],
  "pattern": {{"name": "the sentence's key grammar pattern", "examples": [{{"zh": "new example sentence using the pattern", "en": "its translation"}}]}},
  "mistakes": ["common learner mistakes with this pattern, <=20 words each"]}}

Rules: words[] must cover the sentence in order using ONLY the given tokens
(adjacent tokens may be grouped; skip punctuation). particles[] covers every
function word present. variations and pattern.examples max 2 each; mistakes
max 3. Keep the total tight — this renders on one card."""


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
        else:  # AI drifted from the given tokens: loose containment fallback
            toks = [w for w in zh_tokens if w["t"] and w["t"] in text]
        entry: dict = {"zh": text, "role": chunk.get("role") or chunk.get("note") or ""}
        if toks:
            entry["py"] = " ".join("".join(t.get("py", [])) for t in toks)
            levels = [
                lex_by_id[t["lex"]].hsk_level
                for t in toks if t.get("lex") in lex_by_id and lex_by_id[t["lex"]].hsk_level
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


def explain_sentence(session: Session, sentence: Sentence) -> AiArtifact:
    """Cached AI explanation of one sentence; the cache key is the zh text, so
    re-ingested episodes reuse explanations for unchanged sentences. The AI is
    grounded on the app's own tokenization; pinyin/HSK/POS/glosses are merged
    in from the analysis + lexicon rather than generated."""
    from ..models import Lexeme

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

    words = (sentence.analysis or {}).get("words", [])
    zh_tokens = [w for w in words if w.get("type") == "zh"]
    lex_ids = [w["lex"] for w in zh_tokens if w.get("lex")]
    lex_by_id = {
        lex.id: lex
        for lex in session.scalars(select(Lexeme).where(Lexeme.id.in_(lex_ids)))
    } if lex_ids else {}

    en_line = f"Track translation (context, may be loose): {sentence.en}\n" if sentence.en else ""
    result = provider.complete_json(
        EXPLAIN_PROMPT.format(
            zh=sentence.zh,
            tokens=" | ".join(w["t"] for w in zh_tokens) or sentence.zh,
            en_line=en_line,
        ),
        timeout_s=180,
    )
    if not isinstance(result, dict) or "natural" not in result:
        raise RuntimeError(f"malformed explanation payload: {str(result)[:200]}")

    result["words"] = _merge_breakdown(result.get("words") or [], zh_tokens, lex_by_id)
    for ex in (result.get("pattern") or {}).get("examples") or []:
        if ex.get("zh"):
            ex["py"] = _tts_pinyin(ex["zh"])
    for var in result.get("variations") or []:
        if var.get("zh"):
            var["py"] = _tts_pinyin(var["zh"])
    result["pinyin"] = _sentence_pinyin(words)
    levels = [lex.hsk_level for lex in lex_by_id.values() if lex.hsk_level]
    result["hsk"] = {
        "level": max(levels) if levels else None,
        "offlist": [
            lex.simplified for lex in lex_by_id.values()
            if lex.hsk_level is None and lex.is_dict
        ],
    }

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
