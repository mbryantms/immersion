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
_ner = None

# MSRA tagset -> word payload labels (NE_POS in ingest maps these to ICTCLAS)
NE_LABELS = {"PERSON": "person", "LOCATION": "place", "ORGANIZATION": "org"}
MAX_NAME_LEN = 8


def tokenize(sentences: list[str]) -> list[list[str]]:
    global _tok
    if _tok is None:
        import hanlp

        _tok = hanlp.load(hanlp.pretrained.tok.COARSE_ELECTRA_SMALL_ZH)
    return _tok(sentences)


def ner_entities(token_lists: list[list[str]]) -> list[list[tuple]]:
    """MSRA NER over pre-tokenized sentences -> per-sentence
    (text, tag, token_start, token_end) tuples."""
    global _ner
    if _ner is None:
        import hanlp

        _ner = hanlp.load(hanlp.pretrained.ner.MSRA_NER_ELECTRA_SMALL_ZH)
    return _ner(token_lists)


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


def _tag_names(
    tokens: list[str], entities: list[tuple], lexicon: dict[str, str]
) -> list[tuple[str, str | None]]:
    """(surface, ne-label) pairs. NER entity spans become single tokens; then a
    lexicon pass labels known names NER missed in this sentence and repairs
    tokenizer splits (仙/杜瑞拉 -> 仙杜瑞拉) by merging adjacent tokens whose
    concatenation is a known name."""
    spans: dict[int, tuple[int, str]] = {}
    for text, tag, start, end in entities:
        label = NE_LABELS.get(tag)
        if label and CJK.search(text) and len(text) <= MAX_NAME_LEN:
            spans[start] = (end, label)
    tagged: list[tuple[str, str | None]] = []
    i = 0
    while i < len(tokens):
        if i in spans:
            end, label = spans[i]
            tagged.append(("".join(tokens[i:end]), label))
            i = end
        else:
            tagged.append((tokens[i], None))
            i += 1

    out: list[tuple[str, str | None]] = []
    i = 0
    while i < len(tagged):
        t, label = tagged[i]
        best_end, best_label = None, None
        if CJK.search(t):
            # longest lexicon match, even across NER-labeled tokens: NER often
            # tags only part of a split name (仙 / 杜瑞拉<person>) and the
            # exact-concatenation requirement is the safety here
            concat = t
            if concat in lexicon:
                best_end, best_label = i, lexicon[concat]
            for j in range(i + 1, min(i + 4, len(tagged))):
                nxt, _nxt_label = tagged[j]
                if not CJK.search(nxt):
                    break
                concat += nxt
                if len(concat) > MAX_NAME_LEN:
                    break
                if concat in lexicon:
                    best_end, best_label = j, lexicon[concat]
        if best_end is not None:
            out.append(("".join(s for s, _ in tagged[i : best_end + 1]), best_label))
            i = best_end + 1
        else:
            out.append((t, label))
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


def analyze_sentences(
    sentences: list[str],
    cedict: Cedict | None = None,
    names: dict[str, str] | None = None,
) -> list[list[dict]]:
    """Tokenize pre-split sentences -> per-sentence word lists.

    Word shape: {t, type 'zh'|'x', py[], tones[], gloss[], ne?} — the podreader
    render payload; the ingest layer adds lexeme ids and traditional forms.

    `names` (surface -> person|place|org) seeds the proper-name lexicon —
    typically the series cast from earlier ingests. Entities NER finds across
    this batch are folded in, so a name the tokenizer split in one sentence is
    repaired by its clean occurrences elsewhere. Name tokens bypass the CEDICT
    reconcile re-split: an OOV name stays one tappable word instead of
    shattering into per-character glosses."""
    cedict = cedict or load_cedict()
    token_lists = tokenize(sentences)
    entity_lists = ner_entities(token_lists)

    lexicon = dict(names or {})
    for entities in entity_lists:
        for text, tag, _start, _end in entities:
            label = NE_LABELS.get(tag)
            if label and 2 <= len(text) <= MAX_NAME_LEN and CJK.search(text):
                lexicon.setdefault(text, label)

    result = []
    for tokens, entities in zip(token_lists, entity_lists):
        words = []
        for t, ne in _tag_names(tokens, entities, lexicon):
            for p in [t] if ne else reconcile([t], cedict):
                if not CJK.search(p):
                    words.append({"t": p, "type": "x"})  # latin/digits/punct passthrough
                    continue
                marks, nums = word_pinyin(p)
                w = {"t": p, "type": "zh", "py": marks, "tones": nums}
                gl = cedict.gloss(p)
                if gl:
                    w["gloss"] = gl
                if ne:
                    w["ne"] = ne
                words.append(w)
        result.append(words)
    return result
