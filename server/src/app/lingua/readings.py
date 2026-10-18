"""Explicit dictionary-reading selection for a precise source occurrence."""
from pypinyin.contrib.tone_convert import to_tone, to_tone3
import re


def set_reading(word: dict, reading: str) -> dict:
    syllables = reading.split()
    if len(syllables) != len(word["t"]):
        raise ValueError("Reading needs one syllable per source character")
    if any(not re.fullmatch(r"[A-Za-züÜvV:]+[1-5]?", syllable) for syllable in syllables):
        raise ValueError("Use numbered pinyin syllables, separated by spaces")
    marks = [to_tone(syllable.lower()) for syllable in syllables]
    numbered = [to_tone3(mark, neutral_tone_with_five=True) for mark in marks]
    return {**word, "py": marks, "tones": [int(s[-1]) if s[-1:].isdigit() else 5 for s in numbered],
            "reading": " ".join(numbered), "reading_source": "user"}
