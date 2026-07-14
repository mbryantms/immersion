"""Whisper-timing alignment. Ported from podreader.

Whisper's *text* is discarded — the official transcript is ground truth; only
the word timings are harvested. Per-CJK-char timing is aligned to the
transcript with difflib, then aggregated to per-sentence [t0, t1] spans.

faster-whisper is imported lazily and only ever inside the worker process
(ctranslate2 CUDA runtime; the API process must never pay it)."""

from __future__ import annotations

import difflib
import re
from pathlib import Path

CJK = re.compile(r"[㐀-鿿]")

_model = None


def _preload_cuda_libs() -> None:
    """ctranslate2 dlopens libcublas.so.12/libcudnn.so.9 by SONAME at runtime.
    They come from the nvidia-* pip wheels (the system CUDA is a different
    major), which aren't on the loader path — load them into the process so
    the later dlopen resolves to the already-loaded libraries."""
    import ctypes

    try:
        import nvidia
    except ImportError:
        return
    base = Path(nvidia.__path__[0])
    for pattern in ("cublas/lib/libcublas.so.*", "cublas/lib/libcublasLt.so.*",
                    "cudnn/lib/libcudnn*.so.*"):
        for so in sorted(base.glob(pattern)):
            try:
                ctypes.CDLL(str(so), mode=ctypes.RTLD_GLOBAL)
            except OSError:
                pass


def transcribe_words(audio_path: str) -> list[tuple[str, float, float]]:
    """[(word, start_s, end_s), ...] from faster-whisper word timestamps.
    CUDA large-v3-turbo; falls back to CPU small if the GPU is unavailable."""
    global _model
    from faster_whisper import WhisperModel

    if _model is None:
        try:
            _preload_cuda_libs()
            _model = WhisperModel("large-v3-turbo", device="cuda", compute_type="float16")
        except Exception:
            _model = WhisperModel("small", device="cpu", compute_type="int8")
    try:
        return _run(_model, audio_path)
    except Exception:
        # CUDA problems can surface at encode time, not construction
        _model = WhisperModel("small", device="cpu", compute_type="int8")
        return _run(_model, audio_path)


def _run(model, audio_path: str) -> list[tuple[str, float, float]]:
    segments, _info = model.transcribe(audio_path, language="zh", word_timestamps=True)
    words: list[tuple[str, float, float]] = []
    for seg in segments:
        for w in seg.words or []:
            words.append((w.word.strip(), w.start, w.end))
    return words


def _char_stream(words: list[tuple[str, float, float]]) -> list[tuple[str, float, float]]:
    """Flatten whisper words to per-CJK-char (char, start, end), splitting each
    word's span evenly across its CJK chars; non-CJK words carry no anchor."""
    out: list[tuple[str, float, float]] = []
    for word, start, end in words:
        cjk = [c for c in word if CJK.match(c)]
        if not cjk:
            continue
        dt = (end - start) / len(cjk)
        for i, c in enumerate(cjk):
            out.append((c, start + i * dt, start + (i + 1) * dt))
    return out


def _ends_latin(sent: str) -> bool:
    """True when the last visible content char is Latin/digit (e.g. 我是Nathan。)
    — those chars never match the CJK stream, so the end needs extending."""
    for ch in reversed(sent):
        if CJK.match(ch):
            return False
        if ch.isalnum():
            return True
    return False


def sentence_times(
    sentences: list[str],
    whisper_words: list[tuple[str, float, float]],
) -> list[tuple[float, float]]:
    """Per-sentence (t0_s, t1_s). Unmatched sentences are interpolated between
    neighbors; spans are clamped monotonic with a minimum duration."""
    hyp = _char_stream(whisper_words)
    ref_chars: list[str] = []
    ref_sent_idx: list[int] = []
    for i, sent in enumerate(sentences):
        for ch in sent:
            if CJK.match(ch):
                ref_chars.append(ch)
                ref_sent_idx.append(i)

    times: list[tuple[float, float] | None] = [None] * len(ref_chars)
    matcher = difflib.SequenceMatcher(a=ref_chars, b=[c for c, _, _ in hyp], autojunk=False)
    for block in matcher.get_matching_blocks():
        for k in range(block.size):
            times[block.a + k] = (hyp[block.b + k][1], hyp[block.b + k][2])

    spans: list[list[float] | None] = [None] * len(sentences)
    for idx, t in zip(ref_sent_idx, times):
        if t is None:
            continue
        if spans[idx] is None:
            spans[idx] = [t[0], t[1]]
        else:
            spans[idx][0] = min(spans[idx][0], t[0])
            spans[idx][1] = max(spans[idx][1], t[1])

    # fill gaps and enforce monotonic non-overlapping spans
    result: list[tuple[float, float]] = []
    last_end = 0.0
    for i, span in enumerate(spans):
        if span is None:
            nxt = next((s[0] for s in spans[i + 1 :] if s is not None), last_end + 2.0)
            span = [last_end, max(nxt, last_end)]
        start = max(span[0], last_end)
        end = max(span[1], start + 0.3)
        result.append((start, end))
        last_end = end

    # Latin tails carry no CJK anchor: chain whisper words (any script) forward
    # from the current end while gaps stay ≤1s, never past the next sentence.
    for i, sent in enumerate(sentences):
        if not _ends_latin(sent):
            continue
        start, end = result[i]
        next_t0 = result[i + 1][0] if i + 1 < len(result) else float("inf")
        ext = end
        for _, ws, we in whisper_words:
            if ws >= end and ws <= ext + 1.0 and we <= next_t0:
                ext = max(ext, we)
        if ext > end:
            result[i] = (start, ext)

    return [(round(s, 2), round(e, 2)) for s, e in result]
