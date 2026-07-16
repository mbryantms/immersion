"""Subtitle file -> cues -> sentence segments.

A segment is one or more merged cues: cues are merged while the running text
lacks sentence-final punctuation and the inter-cue gap is small. Multi-sentence
cues are NOT split — cue boundaries are the only honest timing anchors, and
apportioning a cue's span by character count fabricates timestamps that
sentence-replay would then trust."""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path

from ..lingua.pipeline import CJK, SENT_END

CLOSERS = "”』」）)\"'"
MERGE_MAX_GAP_MS = 500
MERGE_MAX_CUES = 4
MERGE_MAX_SPAN_MS = 12_000
DEDUPE_MAX_GAP_MS = 2000


@dataclass
class Cue:
    t0_ms: int
    t1_ms: int
    text: str


@dataclass
class Segment:
    t0_ms: int
    t1_ms: int
    text: str


def sniff_read(path: Path) -> tuple[str, str]:
    """(text, encoding). Chinese subs in the wild are often GBK/GB18030 or Big5."""
    raw = path.read_bytes()
    for enc in ("utf-8-sig", "utf-8"):
        try:
            return raw.decode(enc), enc
        except UnicodeDecodeError:
            pass
    for enc in ("gb18030", "big5"):
        try:
            text = raw.decode(enc)
            # gb18030 rarely *fails*; sanity-check the result looks like CJK text
            if _cjk_ratio(text) > 0.05:
                return text, enc
        except UnicodeDecodeError:
            continue
    from charset_normalizer import from_bytes

    best = from_bytes(raw).best()
    if best is None:
        raise UnicodeDecodeError("unknown", raw[:16], 0, 1, "undecodable subtitle file")
    return str(best), best.encoding


def _cjk_ratio(text: str) -> float:
    visible = [c for c in text if not c.isspace() and not c.isdigit() and c not in ":,->"]
    if not visible:
        return 0.0
    return sum(1 for c in visible if CJK.match(c)) / len(visible)


def cjk_ratio(text: str) -> float:
    return _cjk_ratio(text)


def parse_cues(path: Path, lang: str) -> tuple[list[Cue], str]:
    """Parse SRT/VTT/ASS into clean cues. Returns (cues, encoding)."""
    import pysubs2

    text, encoding = sniff_read(path)
    subs = pysubs2.SSAFile.from_string(text)
    joiner = "" if lang == "zh" else " "
    cues: list[Cue] = []
    for ev in subs.events:
        if ev.is_comment:
            continue
        # plaintext strips ASS override tags; \N becomes newline
        lines = [ln.strip() for ln in ev.plaintext.splitlines()]
        body = joiner.join(ln for ln in lines if ln)
        body = re.sub(r"<[^>]+>", "", body).strip()  # stray HTML-style tags in SRT
        if not body:
            continue
        cues.append(Cue(int(ev.start), int(ev.end), body))
    cues.sort(key=lambda c: (c.t0_ms, c.t1_ms))
    return dedupe_consecutive(cues), encoding


def dedupe_consecutive(cues: list[Cue], max_gap_ms: int = DEDUPE_MAX_GAP_MS) -> list[Cue]:
    """Collapse runs of identical consecutive cues into one spanning cue.

    Two LFC export quirks produce these: frame-sampled zh sidecars chop one
    on-screen line into dozens of contiguous sub-second cues, and some English
    sidecars copy the same paragraph translation across consecutive cues.
    Without this, segment_cues turns the zh runs into repeated sentences —
    or, when the run lacks final punctuation, one sentence with the text
    concatenated several times over."""
    out: list[Cue] = []
    for c in cues:
        if out and c.text == out[-1].text and c.t0_ms - out[-1].t1_ms < max_gap_ms:
            out[-1] = Cue(out[-1].t0_ms, max(out[-1].t1_ms, c.t1_ms), c.text)
        else:
            out.append(Cue(c.t0_ms, c.t1_ms, c.text))
    return out


def _complete(text: str) -> bool:
    """Text ends a sentence (final punct, possibly followed by closing quotes)."""
    t = text.rstrip()
    while t and t[-1] in CLOSERS:
        t = t[:-1]
    return bool(t) and t[-1] in SENT_END


def segment_cues(cues: list[Cue]) -> list[Segment]:
    """Merge cues into sentence segments (zh tracks)."""
    segs: list[Segment] = []
    buf: list[Cue] = []

    def flush():
        if buf:
            segs.append(Segment(buf[0].t0_ms, buf[-1].t1_ms, "".join(c.text for c in buf)))
            buf.clear()

    for cue in cues:
        if buf:
            gap = cue.t0_ms - buf[-1].t1_ms
            runaway = len(buf) >= MERGE_MAX_CUES or cue.t1_ms - buf[0].t0_ms > MERGE_MAX_SPAN_MS
            if gap > MERGE_MAX_GAP_MS or runaway:
                flush()
        buf.append(cue)
        if _complete(cue.text):
            flush()
    flush()
    return segs
