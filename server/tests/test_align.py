"""sentence_times pinned behavior via synthetic word timings (no model)."""

from app.lingua.align import _ends_latin, sentence_times


def words_for(text: str, start: float, per_char: float = 0.5):
    """One whisper 'word' per char, evenly spaced."""
    out = []
    t = start
    for ch in text:
        out.append((ch, t, t + per_char))
        t += per_char
    return out


def test_exact_match():
    sents = ["大家好。", "欢迎回来。"]
    words = words_for("大家好", 0.0) + words_for("欢迎回来", 2.0)
    times = sentence_times(sents, words)
    assert times[0] == (0.0, 1.5)
    assert times[1] == (2.0, 4.0)


def test_whisper_text_disagreement_still_aligns():
    # whisper misheard the middle char; difflib still anchors the rest
    sents = ["大家好。"]
    words = [("大", 0.0, 0.4), ("嫁", 0.4, 0.8), ("好", 0.8, 1.2)]
    (t0, t1), = sentence_times(sents, words)
    assert t0 == 0.0 and t1 == 1.2


def test_unmatched_sentence_interpolates_between_neighbors():
    sents = ["大家好。", "这句没被听到。", "欢迎回来。"]
    words = words_for("大家好", 0.0) + words_for("欢迎回来", 10.0)
    times = sentence_times(sents, words)
    assert times[0] == (0.0, 1.5)
    # gap sentence spans from previous end to next start
    assert times[1][0] == 1.5
    assert times[1][1] <= 10.0
    assert times[2][0] >= times[1][1]


def test_monotonic_and_min_duration():
    sents = ["好。", "好。"]  # identical chars: matcher may map them adjacently
    words = [("好", 5.0, 5.1), ("好", 5.1, 5.2)]
    times = sentence_times(sents, words)
    assert times[0][1] - times[0][0] >= 0.3 - 1e-9
    assert times[1][0] >= times[0][1]


def test_latin_tail_extends_end():
    assert _ends_latin("我是Nathan。")
    assert not _ends_latin("我是内森。")
    sents = ["我是Nathan。", "你呢。"]
    words = (
        words_for("我是", 0.0)
        + [("Nathan", 1.0, 2.0)]  # no CJK anchor
        + words_for("你呢", 5.0)
    )
    times = sentence_times(sents, words)
    assert times[0][1] >= 2.0  # extended over the latin word
    assert times[0][1] <= times[1][0]
