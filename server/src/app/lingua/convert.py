"""Simplified -> Traditional conversion.

Whole-sentence OpenCC conversion is used for display (phrase context picks the
right variant, e.g. 头发→頭髮 vs 发现→發現); s2t is character-count-preserving,
so per-token traditional surfaces are recovered by slicing. If a conversion
ever changes length we fall back to per-token conversion."""

from __future__ import annotations

from functools import lru_cache


@lru_cache(maxsize=1)
def _cc():
    from opencc import OpenCC

    return OpenCC("s2t")


@lru_cache(maxsize=1)
def _cc_t2s():
    from opencc import OpenCC

    return OpenCC("t2s")


def s2t(text: str) -> str:
    return _cc().convert(text)


def t2s(text: str) -> str:
    return _cc_t2s().convert(text)


def zh_norm(text: str) -> str:
    """Match key for comparing sentence text across sources (app sentences vs
    Anki card fields): HTML tags and all whitespace stripped."""
    import re

    return re.sub(r"<[^>]+>|\s+|&nbsp;", "", text)


def sentence_traditional(zh: str, token_spans: list[tuple[int, int]]) -> tuple[str, list[str]]:
    """(full traditional sentence, per-token traditional surfaces)."""
    trad = s2t(zh)
    if len(trad) == len(zh):
        return trad, [trad[a:b] for a, b in token_spans]
    # length drifted (rare): convert tokens independently
    toks = [s2t(zh[a:b]) for a, b in token_spans]
    return trad, toks
