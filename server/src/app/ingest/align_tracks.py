"""zh↔en track alignment: timestamp overlap, nothing fancier.

LFC quirk handled here: some English sidecars copy the same paragraph
translation across several consecutive cues — consecutive identical texts are
collapsed into one span before overlap assignment, otherwise every zh line
would display the whole paragraph."""

from __future__ import annotations

from .subtitles import Cue, Segment


def dedupe_consecutive(cues: list[Cue]) -> list[Cue]:
    out: list[Cue] = []
    for c in cues:
        if out and c.text == out[-1].text and c.t0_ms - out[-1].t1_ms < 2000:
            out[-1] = Cue(out[-1].t0_ms, max(out[-1].t1_ms, c.t1_ms), c.text)
        else:
            out.append(Cue(c.t0_ms, c.t1_ms, c.text))
    return out


def assign_en(segments: list[Segment], en_cues: list[Cue]) -> list[tuple[str | None, float]]:
    """For each zh segment: (english text, overlap confidence 0..1).

    All en cues overlapping the segment are joined (a zh sentence can span
    several short English cues); confidence is covered-time / segment-time."""
    en_cues = dedupe_consecutive(en_cues)
    out: list[tuple[str | None, float]] = []
    for seg in segments:
        hits = []
        covered = 0
        for c in en_cues:
            ov = min(seg.t1_ms, c.t1_ms) - max(seg.t0_ms, c.t0_ms)
            if ov <= 0:
                continue
            # ignore slivers (<15% of the cue barely leans into this segment)
            if ov < 0.15 * (c.t1_ms - c.t0_ms):
                continue
            hits.append((c.t0_ms, c.text))
            covered += ov
        if not hits:
            out.append((None, 0.0))
            continue
        hits.sort()
        text = " ".join(t for _, t in hits)
        conf = min(1.0, covered / max(1, seg.t1_ms - seg.t0_ms))
        out.append((text, round(conf, 3)))
    return out
