"""Analyzed-sentence persistence: tokenize (worker-only, HanLP), link lexemes,
generate traditional, write sentence + token_occurrence rows.

Runs only inside the worker process."""

from __future__ import annotations

import re
import subprocess
from pathlib import Path

from pypinyin import Style, pinyin as py
from sqlalchemy import delete, select, text, update
from sqlalchemy.orm import Session

from ..config import settings
from ..lingua import convert
from ..lingua.cedict import load as load_cedict
from ..lingua.hsk import levels as hsk_levels
from ..lingua.pipeline import analyze_sentences
from ..models import MediaItem, SavedContext, Sentence, Series, TextTrack, TokenOccurrence
from .align_tracks import assign_en
from .subtitles import Segment, parse_cues, segment_cues


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


def get_or_create_lexemes(session: Session, surfaces: set[str]) -> dict[str, int]:
    """surface -> lexeme id; creates OOV lexemes (names etc., is_dict=False)."""
    from ..models import Lexeme

    ids: dict[str, int] = {}
    todo = list(surfaces)
    for i in range(0, len(todo), 900):
        chunk = todo[i : i + 900]
        for lex in session.scalars(select(Lexeme).where(Lexeme.simplified.in_(chunk))):
            ids[lex.simplified] = lex.id
    missing = [s for s in surfaces if s not in ids]
    if missing:
        cedict = load_cedict()
        hsk = hsk_levels()
        for s in missing:
            lex = Lexeme(
                simplified=s,
                traditional=cedict.traditional(s) or convert.s2t(s),
                pinyin=cedict.pinyin(s) or numbered_pinyin(s),
                hsk_level=hsk.get(s),
                is_dict=s in cedict,
            )
            session.add(lex)
        session.flush()
        for lex in session.scalars(select(Lexeme).where(Lexeme.simplified.in_(missing))):
            ids[lex.simplified] = lex.id
    return ids


def write_sentences(
    session: Session,
    item: MediaItem,
    track: TextTrack,
    segments: list[Segment],
    en: list[tuple[str | None, float]] | None,
) -> None:
    """Replace an item's sentences with freshly analyzed ones."""
    words_per_seg = analyze_sentences([s.text for s in segments])

    surfaces = {w["t"] for words in words_per_seg for w in words if w["type"] == "zh"}
    lex_ids = get_or_create_lexemes(session, surfaces)

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
        spans, pos = [], 0
        for w in words:
            spans.append((pos, pos + len(w["t"])))
            pos += len(w["t"])
        trad, trad_toks = convert.sentence_traditional(seg.text, spans)
        for w, tr in zip(words, trad_toks):
            if w["type"] == "zh":
                w["lex"] = lex_ids[w["t"]]
                if tr != w["t"]:
                    w["tr"] = tr
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

    occurrences = [
        TokenOccurrence(
            sentence_id=s.id, idx=i, item_id=item.id,
            surface=w["t"], lexeme_id=w["lex"],
        )
        for s in sentences
        for i, w in enumerate(s.analysis["words"])
        if w["type"] == "zh"
    ]
    session.add_all(occurrences)

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


def ingest_item(session: Session, item_id: int, progress=lambda msg: None) -> None:
    """Full text pipeline for one media item: zh track -> segments -> analysis
    -> en alignment -> thumbnail -> ready."""
    from ..models import MediaRoot

    item = session.get(MediaItem, item_id)
    if item is None or not item.available:
        return
    root = session.get(MediaRoot, item.root_id)
    base = Path(root.path)

    tracks = session.scalars(
        select(TextTrack).where(TextTrack.item_id == item.id, TextTrack.selected)
    ).all()
    zh = next((t for t in tracks if t.lang == "zh"), None)
    en = next((t for t in tracks if t.lang == "en"), None)
    if zh is None or zh.relpath is None:
        progress("no zh track; skipping analysis")
        make_thumb(base / item.relpath, item.id, item.duration_ms)
        return

    progress("parsing subtitles")
    zh_cues, _ = parse_cues(base / zh.relpath, "zh")
    segments = segment_cues(zh_cues)
    en_assign = None
    if en is not None and en.relpath is not None:
        en_cues, _ = parse_cues(base / en.relpath, "en")
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
