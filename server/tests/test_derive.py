"""Passive-exposure knowledge derivation: promotion rules, demotion on lookup,
review graduation write-back, coverage counting familiar."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

from test_api import client, db_session, seeded  # noqa: F401 — fixtures

from app.derive import derive_knowledge
from app.models import Event, KnowledgeState, Lexeme, LexemeStats, SavedItem

NOW = datetime.now(timezone.utc)


def _stats(lexeme_id: int, *, enc=30, items=6, span_days=40, lookups=0):
    return LexemeStats(
        lexeme_id=lexeme_id, encounters=enc, lookups=lookups, distinct_items=items,
        first_seen=NOW - timedelta(days=span_days), last_seen=NOW,
    )


def _lex(session, simplified: str, is_dict=True) -> int:
    lex = Lexeme(simplified=simplified, is_dict=is_dict)
    session.add(lex)
    session.flush()
    return lex.id


def test_promotes_by_evidence_depth(db_session, seeded):  # noqa: F811
    with db_session() as s:
        deep = _lex(s, "深词")
        moderate = _lex(s, "中词")
        shallow = _lex(s, "浅词")
        s.add(_stats(deep, enc=30, items=6, span_days=40))          # known bar
        s.add(_stats(moderate, enc=15, items=3, span_days=20))      # familiar bar
        s.add(_stats(shallow, enc=15, items=2, span_days=20))       # too few items
        s.commit()
        counts = derive_knowledge(s)
        assert counts["known"] == 1 and counts["familiar"] == 1
        assert s.get(KnowledgeState, deep).state == "known"
        assert s.get(KnowledgeState, moderate).state == "familiar"
        assert s.get(KnowledgeState, shallow) is None
        # idempotent: second run promotes nothing new
        counts = derive_knowledge(s)
        assert counts["known"] == 0 and counts["familiar"] == 0


def test_recent_lookup_blocks_promotion(db_session, seeded):  # noqa: F811
    with db_session() as s:
        lex = _lex(s, "查词")
        s.add(_stats(lex, enc=30, items=6, span_days=40, lookups=1))
        s.add(Event(type="lookup", lexeme_id=lex, ts=NOW - timedelta(days=3), client_uuid="lk1"))
        s.commit()
        derive_knowledge(s)
        assert s.get(KnowledgeState, lex) is None
        # an old lookup outside both quiet windows no longer blocks
        s.get(Event, s.scalars(sa_select_event_id(lex)).first()).ts = NOW - timedelta(days=90)
        s.commit()
        derive_knowledge(s)
        assert s.get(KnowledgeState, lex).state == "known"


def sa_select_event_id(lexeme_id):
    from sqlalchemy import select

    return select(Event.id).where(Event.lexeme_id == lexeme_id)


def test_never_touches_manual_anki_ignored_or_saved(db_session, seeded):  # noqa: F811
    with db_session() as s:
        manual = _lex(s, "手词")
        anki = _lex(s, "卡词")
        ignored = _lex(s, "略词")
        saved = _lex(s, "存词")
        for lid in (manual, anki, ignored, saved):
            s.add(_stats(lid, enc=40, items=8, span_days=60))
        s.add(KnowledgeState(lexeme_id=manual, state="learning", source="manual"))
        s.add(KnowledgeState(lexeme_id=anki, state="learning", source="anki"))
        s.add(KnowledgeState(lexeme_id=ignored, state="ignored", source="manual"))
        s.add(SavedItem(kind="word", lexeme_id=saved, surface="存词"))
        s.commit()
        derive_knowledge(s)
        assert s.get(KnowledgeState, manual).state == "learning"
        assert s.get(KnowledgeState, anki).state == "learning"
        assert s.get(KnowledgeState, ignored).state == "ignored"
        assert s.get(KnowledgeState, saved) is None


def test_lookup_event_demotes_derived(client, db_session, seeded):  # noqa: F811
    with db_session() as s:
        s.add(KnowledgeState(lexeme_id=seeded["lexeme"], state="familiar", source="derived"))
        s.commit()
    client.post("/api/events/batch", json=[{
        "client_uuid": "demote-1", "type": "lookup", "lexeme_id": seeded["lexeme"],
    }])
    with db_session() as s:
        ks = s.get(KnowledgeState, seeded["lexeme"])
        assert (ks.state, ks.source) == ("learning", "derived")

    # manual states are NOT demoted by lookups
    with db_session() as s:
        ks = s.get(KnowledgeState, seeded["lexeme"])
        ks.state, ks.source = "known", "manual"
        s.commit()
    client.post("/api/events/batch", json=[{
        "client_uuid": "demote-2", "type": "lookup", "lexeme_id": seeded["lexeme"],
    }])
    with db_session() as s:
        assert s.get(KnowledgeState, seeded["lexeme"]).state == "known"


def test_graduation_needs_three_passes_and_marks_known(client, db_session, seeded):  # noqa: F811
    saved = client.post("/api/saved-items", json={
        "kind": "word", "lexeme_id": seeded["lexeme"], "surface": "你好",
        "sentence_id": seeded["sentence"],
    }).json()
    sid = saved["id"]
    with db_session() as s:  # place at top rung so passes are the only gate
        from app.models import ReviewState

        s.add(ReviewState(saved_item_id=sid, rung=2, passes=0, fails=0, streak=0))
        s.commit()
    r1 = client.post(f"/api/review/{sid}/outcome", json={"result": "pass"}).json()
    r2 = client.post(f"/api/review/{sid}/outcome", json={"result": "pass"}).json()
    assert not r1["graduated"] and not r2["graduated"]
    r3 = client.post(f"/api/review/{sid}/outcome", json={"result": "pass"}).json()
    assert r3["graduated"]
    with db_session() as s:
        ks = s.get(KnowledgeState, seeded["lexeme"])
        assert (ks.state, ks.source) == ("known", "derived")


def test_coverage_counts_familiar(client, db_session, seeded):  # noqa: F811
    assert client.get(f"/api/items/{seeded['item']}").json()["coverage"] == 0
    with db_session() as s:
        s.merge(KnowledgeState(lexeme_id=seeded["lexeme"], state="familiar", source="derived"))
        s.commit()
    body = client.get(f"/api/items/{seeded['item']}").json()
    assert body["coverage"] == 1.0
    assert body["unknown_lexemes"] == 0


def test_recurring_unknowns_excludes_frequent_offlist(client, db_session, seeded):  # noqa: F811
    with db_session() as s:
        from app.models import TokenOccurrence

        # 一个: no HSK level, extremely frequent -> must be filtered as noise
        noise = Lexeme(simplified="一个", is_dict=True, hsk_level=None, freq_rank=20)
        real = Lexeme(simplified="零件", is_dict=True, hsk_level=None, freq_rank=9000)
        s.add_all([noise, real])
        s.flush()
        for i, lid in enumerate([noise.id, real.id]):
            s.add(TokenOccurrence(sentence_id=seeded["sentence"], idx=10 + i,
                                  item_id=seeded["item"], surface="x", lexeme_id=lid))
        s.commit()
    words = {w["simplified"] for w in client.get("/api/stats/dashboard").json()["recurring_unknowns"]}
    assert "零件" in words and "一个" not in words
