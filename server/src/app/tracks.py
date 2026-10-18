"""Available subtitle tracks and durable explicit choices."""

from sqlalchemy import select
from .models import TextTrack


def available(track: TextTrack) -> bool:
    return (track.meta or {}).get("available", True)


def choose_tracks(session, item, persist=True) -> dict:
    tracks = session.scalars(
        select(TextTrack).where(TextTrack.item_id == item.id).order_by(TextTrack.id)
    ).all()
    choices = (item.meta or {}).get("track_choices", {})
    result = {}
    for language in ("zh", "en"):
        candidates = [track for track in tracks if track.lang == language and available(track)]
        if language in choices:
            chosen = next((track for track in candidates if track.id == choices[language]), None)
        else:
            rank = {"sidecar": 0, "embedded": 1, "transcript": 2, "manual": 3, "whisper": 4}
            chosen = (
                min(candidates, key=lambda track: (rank.get(track.source, 9), track.id))
                if candidates
                else None
            )
        for track in tracks:
            if persist and track.lang == language:
                track.selected = track is chosen
        result[language] = chosen
    return result
