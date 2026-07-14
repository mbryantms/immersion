"""CC-CEDICT lookup: simplified word -> (traditional, pinyin, definitions).

Ported from podreader; extended to retain the traditional field, which the
original discarded."""

from __future__ import annotations

import re
from functools import lru_cache
from pathlib import Path

from ..config import settings

LINE = re.compile(r"^(\S+) (\S+) \[([^\]]+)\] /(.+)/$")


class Cedict:
    def __init__(self, path: Path | None = None):
        # simplified -> list of (traditional, numbered_pinyin, [definitions])
        self.entries: dict[str, list[tuple[str, str, list[str]]]] = {}
        with open(path or settings.ref_dir / "cedict.txt", encoding="utf-8") as f:
            for line in f:
                if line.startswith("#"):
                    continue
                m = LINE.match(line.strip())
                if not m:
                    continue
                trad, simp, pinyin, defs = m.groups()
                definitions = [d for d in defs.split("/") if d and not d.startswith("see ")]
                self.entries.setdefault(simp, []).append((trad, pinyin, definitions))

    def __contains__(self, word: str) -> bool:
        return word in self.entries

    def gloss(self, word: str, max_defs: int = 4) -> list[dict]:
        """All senses for a word, trimmed for popover display."""
        out = []
        for _trad, pinyin, defs in self.entries.get(word, []):
            if not defs:
                continue
            out.append({"py": pinyin, "defs": defs[:max_defs]})
        return out

    def traditional(self, word: str) -> str | None:
        """First-listed traditional form."""
        senses = self.entries.get(word)
        return senses[0][0] if senses else None

    def pinyin(self, word: str) -> str | None:
        senses = self.entries.get(word)
        return senses[0][1] if senses else None

    def longest_match(self, text: str, start: int, max_len: int = 8) -> str | None:
        """Longest dictionary word in text beginning at start."""
        end = min(len(text), start + max_len)
        for stop in range(end, start, -1):
            if text[start:stop] in self.entries:
                return text[start:stop]
        return None


@lru_cache(maxsize=1)
def load() -> Cedict:
    return Cedict()
