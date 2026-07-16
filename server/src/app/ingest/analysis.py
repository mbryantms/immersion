"""Analyzed-sentence persistence: tokenize (worker-only, HanLP), link lexemes,
generate traditional, write sentence + token_occurrence rows.

Runs only inside the worker process."""

from __future__ import annotations

import re
import subprocess
from collections import Counter
from pathlib import Path

from pypinyin import Style, pinyin as py
from sqlalchemy import delete, select, text, update
from sqlalchemy.orm import Session

from ..config import settings
from ..lingua import convert
from ..lingua.cedict import load as load_cedict
from ..lingua.hsk import levels as hsk_levels
from ..lingua.pipeline import analyze_sentences
from ..models import (
    MediaItem,
    SavedContext,
    Sentence,
    Series,
    SeriesName,
    TextTrack,
    TokenOccurrence,
)
from .align_tracks import assign_en
from .subtitles import Segment, parse_cues, segment_cues

NE_POS = {"person": "nr", "place": "ns", "org": "nt"}  # word ne -> ICTCLAS tag


def numbered_pinyin(word: str) -> str:
    return " ".join(s[0] for s in py(word, style=Style.TONE3, neutral_tone_with_five=True))


CJK_RE = re.compile(r"[㐀-鿿]")


def fts_row(sentence: Sentence) -> tuple:
    """Pre-segmented columns for sentence_fts (unicode61 can't segment CJK):
    space-joined HanLP tokens, space-joined chars (substring matches via
    phrase queries), traditional tokens, toneless pinyin, english."""
    words = (sentence.analysis or {}).get("words", [])
    zh_words = " ".join(w["t"] for w in words if w["type"] == "zh")
    zh_chars = " ".join(ch for ch in sentence.zh if CJK_RE.match(ch))
    trad_words = " ".join(w.get("tr", w["t"]) for w in words if w["type"] == "zh")
    toneless = " ".join(s[0] for s in py(sentence.zh, style=Style.NORMAL) if s[0].strip())
    return (sentence.id, zh_words, zh_chars, trad_words, toneless, sentence.en or "")


def write_fts(session: Session, sentences: list[Sentence]) -> None:
    for s in sentences:
        rowid, *cols = fts_row(s)
        session.execute(
            text("INSERT INTO sentence_fts(rowid, zh_words, zh_chars, trad_words, pinyin, en) "
                 "VALUES (:rowid, :zh_words, :zh_chars, :trad_words, :pinyin, :en)"),
            {"rowid": rowid, "zh_words": cols[0], "zh_chars": cols[1],
             "trad_words": cols[2], "pinyin": cols[3], "en": cols[4]},
        )


def get_or_create_lexemes(
    session: Session, surfaces: set[str], names: dict[str, str] | None = None
) -> dict[str, int]:
    """surface -> lexeme id; creates OOV lexemes (names etc., is_dict=False).
    `names` (surface -> ne label) stamps an ICTCLAS name tag on OOV lexemes so
    the gloss sheet shows a name/place/organization chip."""
    from ..models import Lexeme

    names = names or {}
    ids: dict[str, int] = {}
    todo = list(surfaces)
    for i in range(0, len(todo), 900):
        chunk = todo[i : i + 900]
        for lex in session.scalars(select(Lexeme).where(Lexeme.simplified.in_(chunk))):
            ids[lex.simplified] = lex.id
            if not lex.is_dict and lex.pos is None and lex.simplified in names:
                lex.pos = NE_POS.get(names[lex.simplified])
    missing = [s for s in surfaces if s not in ids]
    if missing:
        cedict = load_cedict()
        hsk = hsk_levels()
        for s in missing:
            in_dict = s in cedict
            lex = Lexeme(
                simplified=s,
                traditional=cedict.traditional(s) or convert.s2t(s),
                pinyin=cedict.pinyin(s) or numbered_pinyin(s),
                hsk_level=hsk.get(s),
                is_dict=in_dict,
                pos=None if in_dict else NE_POS.get(names.get(s, "")),
            )
            session.add(lex)
        session.flush()
        for lex in session.scalars(select(Lexeme).where(Lexeme.simplified.in_(missing))):
            ids[lex.simplified] = lex.id
    return ids


def series_name_lexicon(session: Session, item: MediaItem) -> dict[str, str]:
    """Cast lexicon accumulated for the item's series: surface -> ne label."""
    if not item.series_id:
        return {}
    rows = session.scalars(select(SeriesName).where(SeriesName.series_id == item.series_id))
    return {r.simplified: r.label for r in rows}


def record_series_names(session: Session, item: MediaItem, words_per_seg: list[list[dict]]) -> None:
    """Fold this ingest's NER findings into the series cast lexicon. Counts
    track the max seen in a single ingest so reanalysis doesn't double-count."""
    if not item.series_id:
        return
    counts: Counter[str] = Counter()
    labels: dict[str, str] = {}
    for words in words_per_seg:
        for w in words:
            ne = w.get("ne")
            if ne and len(w["t"]) >= 2:
                counts[w["t"]] += 1
                labels.setdefault(w["t"], ne)
    if not counts:
        return
    existing = {
        r.simplified: r
        for r in session.scalars(select(SeriesName).where(SeriesName.series_id == item.series_id))
    }
    for surface, n in counts.items():
        row = existing.get(surface)
        if row is None:
            session.add(SeriesName(
                series_id=item.series_id, simplified=surface, label=labels[surface], count=n,
            ))
        else:
            row.count = max(row.count, n)
    session.flush()


def link_words(zh: str, words: list[dict], lex_ids: dict[str, int]) -> str:
    """Attach lexeme ids + traditional surfaces in place; returns the full
    traditional sentence."""
    spans, pos = [], 0
    for w in words:
        spans.append((pos, pos + len(w["t"])))
        pos += len(w["t"])
    trad, trad_toks = convert.sentence_traditional(zh, spans)
    for w, tr in zip(words, trad_toks):
        if w["type"] == "zh":
            w["lex"] = lex_ids[w["t"]]
            if tr != w["t"]:
                w["tr"] = tr
    return trad


def token_occurrences(item_id: int, sentences: list[Sentence]) -> list[TokenOccurrence]:
    return [
        TokenOccurrence(
            sentence_id=s.id, idx=i, item_id=item_id,
            surface=w["t"], lexeme_id=w["lex"],
        )
        for s in sentences
        for i, w in enumerate(s.analysis["words"])
        if w["type"] == "zh"
    ]


def write_sentences(
    session: Session,
    item: MediaItem,
    track: TextTrack,
    segments: list[Segment],
    en: list[tuple[str | None, float]] | None,
) -> None:
    """Replace an item's sentences with freshly analyzed ones."""
    words_per_seg = analyze_sentences(
        [s.text for s in segments], names=series_name_lexicon(session, item)
    )
    record_series_names(session, item, words_per_seg)

    surfaces = {w["t"] for words in words_per_seg for w in words if w["type"] == "zh"}
    name_words = {w["t"]: w["ne"] for words in words_per_seg for w in words if w.get("ne")}
    lex_ids = get_or_create_lexemes(session, surfaces, name_words)

    # unlink saved contexts (snapshot keeps the data), then drop old rows
    old_ids = [i for (i,) in session.execute(select(Sentence.id).where(Sentence.item_id == item.id))]
    if old_ids:
        session.execute(
            update(SavedContext).where(SavedContext.sentence_id.in_(old_ids)).values(sentence_id=None)
        )
        for i in range(0, len(old_ids), 500):
            chunk = old_ids[i : i + 500]
            session.execute(
                text(f"DELETE FROM sentence_fts WHERE rowid IN ({','.join(map(str, chunk))})")
            )
    session.execute(delete(TokenOccurrence).where(TokenOccurrence.item_id == item.id))
    session.execute(delete(Sentence).where(Sentence.item_id == item.id))

    sentences: list[Sentence] = []
    for ord_, (seg, words) in enumerate(zip(segments, words_per_seg)):
        trad = link_words(seg.text, words, lex_ids)
        en_text, conf = en[ord_] if en else (None, 0.0)
        sentences.append(Sentence(
            item_id=item.id, track_id=track.id, ordinal=ord_,
            zh=seg.text, trad=trad if trad != seg.text else None,
            t0_ms=seg.t0_ms, t1_ms=seg.t1_ms,
            en=en_text, en_source="track" if en_text else None,
            align_conf=conf if en_text else None,
            analysis={"words": words},
        ))
    session.add_all(sentences)
    session.flush()

    session.add_all(token_occurrences(item.id, sentences))

    write_fts(session, sentences)

    # re-link surviving saved contexts by exact zh match
    by_zh = {s.zh: s.id for s in sentences}
    orphans = session.scalars(
        select(SavedContext).where(SavedContext.sentence_id.is_(None))
    )
    for ctx in orphans:
        snap = ctx.snapshot or {}
        if snap.get("item_id") == item.id and snap.get("zh") in by_zh:
            ctx.sentence_id = by_zh[snap["zh"]]
    session.flush()


def reanalyze_item(session: Session, item_id: int, progress=lambda msg: None) -> dict:
    """Re-run token/NER analysis over an item's existing sentences, in place.

    Keeps the sentence rows themselves — ids, timings, en (whisper/AI work),
    saved-context links — and rebuilds only analysis JSON, token_occurrence
    and FTS. This is the backfill path for pipeline changes: no subtitle
    re-parse, no whisper, no re-translation."""
    item = session.get(MediaItem, item_id)
    if item is None:
        return {"skipped": "no item"}
    sentences = session.scalars(
        select(Sentence).where(Sentence.item_id == item.id).order_by(Sentence.ordinal)
    ).all()
    if not sentences:
        return {"skipped": "no sentences"}

    progress(f"reanalyzing {len(sentences)} sentences")
    words_per_seg = analyze_sentences(
        [s.zh for s in sentences], names=series_name_lexicon(session, item)
    )
    record_series_names(session, item, words_per_seg)

    surfaces = {w["t"] for words in words_per_seg for w in words if w["type"] == "zh"}
    name_words = {w["t"]: w["ne"] for words in words_per_seg for w in words if w.get("ne")}
    lex_ids = get_or_create_lexemes(session, surfaces, name_words)

    for s, words in zip(sentences, words_per_seg):
        link_words(s.zh, words, lex_ids)
        s.analysis = {"words": words}

    session.execute(delete(TokenOccurrence).where(TokenOccurrence.item_id == item.id))
    session.add_all(token_occurrences(item.id, sentences))

    ids = [s.id for s in sentences]
    for i in range(0, len(ids), 500):
        chunk = ids[i : i + 500]
        session.execute(
            text(f"DELETE FROM sentence_fts WHERE rowid IN ({','.join(map(str, chunk))})")
        )
    write_fts(session, sentences)

    # cache-buster: sentence ids didn't change, so the payload ETag needs this
    item.meta = {**(item.meta or {}), "analysis_rev": (item.meta or {}).get("analysis_rev", 0) + 1}
    session.commit()
    return {"sentences": len(sentences)}


def make_thumb(video_path: Path, item_id: int, duration_ms: int | None) -> None:
    settings.thumb_dir.mkdir(parents=True, exist_ok=True)
    out = settings.thumb_dir / f"{item_id}.jpg"
    if out.exists():
        return
    seek = (duration_ms or 60_000) / 2000
    subprocess.run(
        ["ffmpeg", "-v", "quiet", "-ss", f"{seek:.1f}", "-i", str(video_path),
         "-frames:v", "1", "-vf", "scale=480:-2", "-y", str(out)],
        check=False,
    )


def resolve_track_path(base: str | Path, item: MediaItem, track: TextTrack) -> Path | None:
    """Filesystem path holding a track's cues. Sidecars live under the root;
    embedded tracks live in the subs cache (re-extracted if it was wiped)."""
    if track.source == "sidecar" and track.relpath:
        return Path(base) / track.relpath
    if track.source == "embedded":
        from .embedded import extract_stream, sub_path

        idx = (track.meta or {}).get("stream_index")
        if idx is None:
            return None
        path = sub_path(item.id, idx)
        if path.exists() or extract_stream(Path(base) / item.relpath, idx, path):
            return path
    return None


def _pick_track(tracks: list[TextTrack], lang: str) -> TextTrack | None:
    """Best parseable track for a language: sidecar beats embedded."""
    rank = {"sidecar": 0, "embedded": 1}
    candidates = [t for t in tracks if t.lang == lang and t.source in rank]
    return min(candidates, key=lambda t: rank[t.source]) if candidates else None


def _setting_true(session: Session, key: str) -> bool:
    from ..models import Setting

    row = session.get(Setting, key)
    return bool(row.value) if row is not None else False


def ingest_item(session: Session, item_id: int, progress=lambda msg: None) -> None:
    """Full text pipeline for one media item: zh track -> segments -> analysis
    -> en alignment -> thumbnail -> ready."""
    from ..jobs import enqueue
    from ..models import MediaRoot

    item = session.get(MediaItem, item_id)
    if item is None or not item.available:
        return
    root = session.get(MediaRoot, item.root_id)
    base = Path(root.path)

    tracks = session.scalars(
        select(TextTrack).where(TextTrack.item_id == item.id, TextTrack.selected)
    ).all()
    zh = _pick_track(tracks, "zh")
    en = _pick_track(tracks, "en")
    if (zh is None or en is None) and item.kind == "video":
        from .embedded import ensure_embedded_tracks

        ensure_embedded_tracks(session, item, base / item.relpath)
        tracks = session.scalars(
            select(TextTrack).where(TextTrack.item_id == item.id, TextTrack.selected)
        ).all()
        zh = zh or _pick_track(tracks, "zh")
        en = en or _pick_track(tracks, "en")

    zh_path = resolve_track_path(base, item, zh) if zh else None
    if zh_path is None:
        make_thumb(base / item.relpath, item.id, item.duration_ms)
        whisper = next((t for t in tracks if t.lang == "zh" and t.source == "whisper"), None)
        if whisper is not None and item.ready:
            progress("keeping whisper-generated transcript")
        elif item.kind == "video" and _setting_true(session, "whisper_unsubbed"):
            # low priority: subtitle ingests should never wait on GPU work
            enqueue(session, "whisper_transcribe", {"item_id": item.id}, priority=-1)
            progress("no zh track; queued whisper transcription")
        else:
            progress("no zh track; skipping analysis")
        session.commit()
        return

    progress("parsing subtitles")
    zh_cues, _ = parse_cues(zh_path, "zh")
    segments = segment_cues(zh_cues)
    en_assign = None
    en_path = resolve_track_path(base, item, en) if en else None
    if en_path is not None:
        en_cues, _ = parse_cues(en_path, "en")
        en_assign = assign_en(segments, en_cues)

    progress(f"analyzing {len(segments)} sentences")
    write_sentences(session, item, zh, segments, en_assign)

    make_thumb(base / item.relpath, item.id, item.duration_ms)
    item.ready = True
    if item.series_id:
        series = session.get(Series, item.series_id)
        if series and series.cover_item_id is None:
            series.cover_item_id = item.id
    session.commit()
