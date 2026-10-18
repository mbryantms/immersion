"""Effective subtitle timing used by playback, review, search, and export."""

from sqlalchemy.orm import Session

from .models import Sentence, TextTrack


def effective_times(session: Session, sentence: Sentence) -> tuple[int, int]:
    track = session.get(TextTrack, sentence.track_id)
    offset = track.offset_ms if track else 0
    return max(0, sentence.t0_ms + offset), max(0, sentence.t1_ms + offset)
