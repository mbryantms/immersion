"""Source-specific script equivalence using OpenCC's one-to-one character pairs.

Ambiguous one-to-many and many-to-one mappings are deliberately excluded.
See SCRIPT_PAIRS.md for provenance and regeneration.
"""
import json
from functools import lru_cache
from pathlib import Path


@lru_cache(maxsize=1)
def _pairs() -> dict[str, str]:
    pairs = json.loads(Path(__file__).with_name("script_pairs.json").read_text(encoding="utf-8"))
    return {**pairs, **{traditional: simple for simple, traditional in pairs.items()}}


def script_variants(source: str) -> dict[str, str]:
    pairs = _pairs()
    return {pairs[ch]: ch for ch in source if ch in pairs and pairs[ch] not in source}
