"""Dictation LCS scoring — must stay in sync with web/src/lib/dictation.ts."""

from app.lingua.diff import lcs_ops, norm_zh, score_attempt


def test_norm_keeps_names_and_numbers():
    assert norm_zh("大家好！Hello, 你们 好。１２") == "大家好hello你们好12"


def test_perfect_and_empty():
    assert score_attempt("大家好。", "大家好").score == 1.0
    assert score_attempt("大家好。", "").score == 0.0
    assert score_attempt("！！", "whatever").score == 0.0
    assert score_attempt("！！", "").score == 1.0


def test_missing_and_extra_chars():
    r = score_attempt("大家好", "大好")
    assert r.score == 2 / 3
    assert ("del", "家") in r.ops

    r = score_attempt("大家好", "大家很好")
    assert r.score == 0.75
    assert ("ins", "很") in r.ops


def test_substitution_counts_once():
    r = score_attempt("大家好", "大蒙好")
    assert r.score == 2 / 3
    ops = set(r.ops)
    assert ("del", "家") in ops and ("ins", "蒙") in ops


def test_lcs_not_greedy():
    # greedy matching would pair the first 好 wrong; LCS recovers both 好
    assert [op for op, _ in lcs_ops("好好学", "好学")].count("eq") == 2
