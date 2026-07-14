"""First-boot dictionary import: CC-CEDICT + HSK30 -> lexeme/sense tables,
jieba lexicon -> part of speech + frequency rank, Tatoeba -> example pairs.

Gives every dictionary word a stable row id before any media references it
(canonical lexical identity, spec ARCH-002). ~125k lexemes + ~140k senses;
bulk-inserted with client-assigned ids in a few seconds."""

from __future__ import annotations

import csv

from sqlalchemy import func, insert, select, update
from sqlalchemy.orm import Session

from .config import settings
from .lingua.cedict import load as load_cedict
from .lingua.hsk import levels as hsk_levels
from .models import ExampleSentence, Lexeme, Sense


def dictionary_imported(session: Session) -> bool:
    return bool(session.scalar(select(func.count()).select_from(Lexeme).where(Lexeme.is_dict)))


def import_word_extras(session: Session) -> dict:
    """jieba lexicon (word count pos) -> lexeme.pos/freq_rank; idempotent-ish:
    skipped when any lexeme already carries a rank."""
    path = settings.ref_dir / "jieba_dict.txt"
    if not path.exists():
        return {"skipped": "no jieba_dict.txt"}
    if session.scalar(select(Lexeme.id).where(Lexeme.freq_rank.is_not(None)).limit(1)):
        return {"skipped": True}
    entries: dict[str, tuple[int, str]] = {}
    for line in path.read_text().splitlines():
        parts = line.split()
        if len(parts) >= 2 and parts[1].isdigit():
            entries[parts[0]] = (int(parts[1]), parts[2] if len(parts) > 2 else "")
    ranked = sorted(entries.items(), key=lambda kv: -kv[1][0])
    rank_of = {w: r + 1 for r, (w, _) in enumerate(ranked)}
    updated = 0
    for lex_id, simp in session.execute(select(Lexeme.id, Lexeme.simplified)):
        e = entries.get(simp)
        if e is None:
            continue
        session.execute(
            update(Lexeme).where(Lexeme.id == lex_id)
            .values(pos=e[1] or None, freq_rank=rank_of[simp])
        )
        updated += 1
    session.commit()
    return {"pos_freq_updated": updated}


def import_examples(session: Session) -> dict:
    """Tatoeba zh-en pairs; zh_simp normalized via OpenCC for matching."""
    path = settings.ref_dir / "tatoeba_cmn_eng.tsv"
    if not path.exists():
        return {"skipped": "no tatoeba_cmn_eng.tsv"}
    if session.scalar(select(func.count()).select_from(ExampleSentence)):
        return {"skipped": True}
    from .lingua import convert

    rows = []
    with open(path, newline="") as f:
        for zh, en in csv.reader(f, delimiter="\t"):
            rows.append({"zh": zh, "zh_simp": convert.t2s(zh), "en": en, "source": "tatoeba"})
    for i in range(0, len(rows), 5000):
        session.execute(insert(ExampleSentence), rows[i : i + 5000])
    session.commit()
    return {"examples": len(rows)}


def import_dictionary(session: Session) -> dict:
    if dictionary_imported(session):
        return {"skipped": True}
    cedict = load_cedict()
    hsk = hsk_levels()

    start = (session.scalar(select(func.max(Lexeme.id))) or 0) + 1
    lex_rows, sense_rows = [], []
    for i, (simp, entries) in enumerate(cedict.entries.items()):
        lid = start + i
        trad, pinyin, _ = entries[0]
        lex_rows.append({
            "id": lid, "simplified": simp, "traditional": trad, "pinyin": pinyin,
            "hsk_level": hsk.get(simp), "is_dict": True,
        })
        for ord_, (etrad, epy, defs) in enumerate(entries):
            if not defs:
                continue
            sense_rows.append({
                "lexeme_id": lid, "ord": ord_, "source": "cedict",
                "traditional": etrad, "pinyin": epy, "glosses": defs,
            })

    for i in range(0, len(lex_rows), 5000):
        session.execute(insert(Lexeme), lex_rows[i : i + 5000])
    for i in range(0, len(sense_rows), 5000):
        session.execute(insert(Sense), sense_rows[i : i + 5000])
    session.commit()
    return {"lexemes": len(lex_rows), "senses": len(sense_rows)}
