"""HSK 3.0 word->level (1-7; 7 stands for the merged HSK 7-9 band)."""

from __future__ import annotations

import json
from functools import lru_cache

from ..config import settings


@lru_cache(maxsize=1)
def levels() -> dict[str, int]:
    with open(settings.ref_dir / "hsk30.json", encoding="utf-8") as f:
        return json.load(f)
