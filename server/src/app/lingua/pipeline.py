"""Text -> sentences of words with pinyin, tones, glosses. Ported from podreader.

HanLP is imported lazily and only ever inside the worker process — the API
process must never pay the torch import."""

from __future__ import annotations

import re

from pypinyin import Style, pinyin as py

from .cedict import Cedict, load as load_cedict

SENT_END = "。！？!?…"
CJK = re.compile(r"[㐀-鿿]")


def split_sentences(text: str) -> list[str]:
    """Split on Chinese sentence-final punctuation, keeping the punctuation."""
    text = re.sub(r"[\s﻿]+", "", text)  # spacing carries no meaning in a zh transcript
    out, buf = [], ""
    for ch in text:
        buf += ch
        if ch in SENT_END:
            out.append(buf)
            buf = ""
    if buf:
        out.append(buf)
    # reattach closing quotes/brackets that follow sentence-final punctuation
    merged: list[str] = []
    for s in out:
        if merged and s and s[0] in "”』」）)":
            merged[-1] += s[0]
            s = s[1:]
        if s:
            merged.append(s)
    return merged


_tok = None


def tokenize(sentences: list[str]) -> list[list[str]]:
    global _tok
    if _tok is None:
        import hanlp

        _tok = hanlp.load(hanlp.pretrained.tok.COARSE_ELECTRA_SMALL_ZH)
    return _tok(sentences)


def reconcile(tokens: list[str], cedict: Cedict) -> list[str]:
    """Ensure every multi-char CJK token maps to a CEDICT entry; if not, re-split
    it with longest-match so per-word glosses always resolve."""
    out: list[str] = []
    for t in tokens:
        if len(t) < 2 or not CJK.search(t) or t in cedict:
            out.append(t)
            continue
        i = 0
        while i < len(t):
            m = cedict.longest_match(t, i)
            if m:
                out.append(m)
                i += len(m)
            else:
                out.append(t[i])
                i += 1
    return out


def word_pinyin(word: str) -> tuple[list[str], list[int]]:
    """Per-character display pinyin (tone marks) and tone numbers (5 = neutral)."""
    marks = [s[0] for s in py(word, style=Style.TONE)]
    nums = []
    for s in py(word, style=Style.TONE3, neutral_tone_with_five=True):
        m = re.search(r"(\d)$", s[0])
        nums.append(int(m.group(1)) if m else 5)
    return marks, nums


def analyze_sentences(sentences: list[str], cedict: Cedict | None = None) -> list[list[dict]]:
    """Tokenize pre-split sentences -> per-sentence word lists.

    Word shape: {t, type 'zh'|'x', py[], tones[], gloss[]} — the podreader
    render payload; the ingest layer adds lexeme ids and traditional forms."""
    cedict = cedict or load_cedict()
    token_lists = tokenize(sentences)
    result = []
    for tokens in token_lists:
        words = []
        for t in reconcile(tokens, cedict):
            if not CJK.search(t):
                words.append({"t": t, "type": "x"})  # latin/digits/punct passthrough
                continue
            marks, nums = word_pinyin(t)
            w = {"t": t, "type": "zh", "py": marks, "tones": nums}
            gl = cedict.gloss(t)
            if gl:
                w["gloss"] = gl
            words.append(w)
        result.append(words)
    return result
