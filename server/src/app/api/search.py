"""Full-text search over analyzed sentences (hanzi / traditional / pinyin /
english) with jump-to-timestamp results, plus per-lexeme concordance.

sentence_fts holds pre-segmented columns (unicode61 can't segment CJK):
CJK queries match the space-joined char column as a phrase, so substrings
crossing token boundaries still hit; latin queries hit pinyin + english."""

from __future__ import annotations

import re
import unicodedata

from fastapi import APIRouter, Depends, Query
from sqlalchemy import func, select, text
from sqlalchemy.orm import Session

from ..db import get_session
from ..models import ExampleSentence, Lexeme, MediaItem, Sentence, TokenOccurrence
from ..lingua.convert import t2s
from ..timing import effective_times

router = APIRouter()

CJK = re.compile(r"[㐀-鿿]")


def _fts_query(q: str) -> str:
    """CJK input -> phrase over spaced chars ('磨坊主' -> '"磨 坊 主"');
    anything else -> prefix-matched terms over pinyin/en columns."""
    q = t2s(unicodedata.normalize("NFKC", q.strip()))
    if CJK.search(q):
        chars = " ".join(ch for ch in q if CJK.match(ch))
        return f'"{chars}"'
    q = "".join(ch for ch in unicodedata.normalize("NFD", q.lower())
                if unicodedata.category(ch) != "Mn")
    terms = re.findall(r"[^\W_]+", q, flags=re.UNICODE)
    # Treat input as literal terms, never as FTS operators or column selectors.
    # A single alphanumeric term may be an English identifier (e.g. en1).
    # Numbered, spaced syllable sequences are unambiguously pinyin input.
    if len(terms) > 1 and all(re.fullmatch(r"[a-z]+[1-5]", term) for term in terms):
        terms = [term[:-1] for term in terms]
    return " ".join(f'"{term}"*' for term in terms)


def _result(session: Session, s: Sentence) -> dict:
    item = session.get(MediaItem, s.item_id)
    t0, t1 = effective_times(session, s)
    return {
        "sentence_id": s.id,
        "item_id": s.item_id,
        "item_title": item.title if item else None,
        "item_kind": item.kind if item else None,
        "zh": s.zh,
        "trad": s.trad,
        "en": s.en,
        "t0_ms": t0,
        "t1_ms": t1,
    }


@router.get("/search")
def search(
    q: str = Query(min_length=1, max_length=100),
    limit: int = 30,
    session: Session = Depends(get_session),
):
    match = _fts_query(q)
    if not match:
        return {"query": q, "results": []}
    rows = session.execute(
        text("SELECT rowid FROM sentence_fts WHERE sentence_fts MATCH :m ORDER BY rank LIMIT :n"),
        {"m": match, "n": min(limit, 100)},
    ).all()
    sentences = {
        s.id: s
        for s in session.scalars(select(Sentence).where(Sentence.id.in_([r[0] for r in rows])))
    }
    ordered = [sentences[r[0]] for r in rows if r[0] in sentences]
    return {"query": q, "results": [_result(session, s) for s in ordered]}


@router.get("/lexemes/{lexeme_id}/examples")
def examples(lexeme_id: int, limit: int = 5, session: Session = Depends(get_session)):
    """Curated Tatoeba examples containing the word, shortest first (short
    sentences make the best dictionary examples)."""
    lex = session.get(Lexeme, lexeme_id)
    if lex is None:
        return {"lexeme_id": lexeme_id, "results": []}
    rows = session.scalars(
        select(ExampleSentence)
        .where(ExampleSentence.zh_simp.contains(lex.simplified))
        .order_by(func.length(ExampleSentence.zh_simp))
        .limit(min(limit, 20))
    ).all()
    return {
        "lexeme_id": lexeme_id,
        "results": [{"zh": e.zh_simp, "en": e.en, "source": e.source} for e in rows],
    }


@router.get("/lexemes/{lexeme_id}/concordance")
def concordance(lexeme_id: int, limit: int = 20, session: Session = Depends(get_session)):
    """Every sentence containing the lexeme, newest items first."""
    rows = session.execute(
        select(TokenOccurrence.sentence_id)
        .where(TokenOccurrence.lexeme_id == lexeme_id)
        .group_by(TokenOccurrence.sentence_id)
        .order_by(TokenOccurrence.sentence_id.desc())
        .limit(min(limit, 100))
    ).all()
    sentences = session.scalars(
        select(Sentence).where(Sentence.id.in_([r[0] for r in rows])).order_by(Sentence.id.desc())
    ).all()
    return {"lexeme_id": lexeme_id, "results": [_result(session, s) for s in sentences]}
