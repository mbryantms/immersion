"""Dictation diff scoring. Ported from podreader's in-page LCS implementation
(the reader's JS), kept in sync with web/src/lib/dictation.ts — the web app
scores locally for instant feedback; this is the server-side reference used by
the review queue.

Only CJK characters count: punctuation and spacing aren't listening skill."""

from __future__ import annotations

import re
from dataclasses import dataclass

CJK = re.compile(r"[㐀-鿿]")


def norm_zh(text: str) -> str:
    return "".join(ch for ch in text if CJK.match(ch))


def lcs_ops(a: str, b: str) -> list[tuple[str, str]]:
    """LCS edit script from expected `a` to typed `b`:
    ('eq', ch) | ('del', ch) missing from b | ('ins', ch) extra in b."""
    n, m = len(a), len(b)
    # DP table of LCS lengths, then walk back to recover the script
    table = [[0] * (m + 1) for _ in range(n + 1)]
    for i in range(n - 1, -1, -1):
        for j in range(m - 1, -1, -1):
            if a[i] == b[j]:
                table[i][j] = table[i + 1][j + 1] + 1
            else:
                table[i][j] = max(table[i + 1][j], table[i][j + 1])
    ops: list[tuple[str, str]] = []
    i = j = 0
    while i < n and j < m:
        if a[i] == b[j]:
            ops.append(("eq", a[i]))
            i += 1
            j += 1
        elif table[i + 1][j] >= table[i][j + 1]:
            ops.append(("del", a[i]))
            i += 1
        else:
            ops.append(("ins", b[j]))
            j += 1
    ops.extend(("del", ch) for ch in a[i:])
    ops.extend(("ins", ch) for ch in b[j:])
    return ops


@dataclass
class DictationResult:
    score: float  # matched chars / expected chars; 1.0 when expected is empty
    ops: list[tuple[str, str]]


PASS_SCORE = 0.95  # same threshold the reader UI marks green


def score_attempt(expected_zh: str, typed: str) -> DictationResult:
    expected = norm_zh(expected_zh)
    typed_n = norm_zh(typed)
    if not expected:
        return DictationResult(score=1.0, ops=[])
    ops = lcs_ops(expected, typed_n)
    ok = sum(1 for op, _ in ops if op == "eq")
    return DictationResult(score=ok / len(expected), ops=ops)
