"""Review queue: implicit enrollment, ladder moves, graduation, fresh-context
preference; plus FTS search round-trip on a temp DB."""

from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import text
from sqlalchemy.orm import sessionmaker

from app.db import get_session, make_engine
from app.ingest.analysis import write_fts
from app.main import app
from app.models import (
    Base,
    Lexeme,
    MediaItem,
    MediaRoot,
    ReviewState,
    SavedContext,
    SavedItem,
    Sentence,
    TextTrack,
    TokenOccurrence,
)


@pytest.fixture()
def db_session(tmp_path: Path):
    engine = make_engine(tmp_path / "test.db")
    Base.metadata.create_all(engine)
    with engine.connect() as c:
        c.execute(text(
            "CREATE VIRTUAL TABLE sentence_fts USING fts5("
            "zh_words, zh_chars, trad_words, pinyin, en)"
        ))
        c.commit()
    Session = sessionmaker(engine, expire_on_commit=False)

    def override():
        with Session() as s:
            yield s

    app.dependency_overrides[get_session] = override
    yield Session
    app.dependency_overrides.clear()


@pytest.fixture()
def client(db_session):
    return TestClient(app)


@pytest.fixture()
def seeded(db_session):
    with db_session() as s:
        root = MediaRoot(slug="x", kind="video", path="/tmp/x")
        s.add(root)
        s.flush()
        item = MediaItem(root_id=root.id, relpath="a.mp4", title="ep", kind="video")
        s.add(item)
        s.flush()
        track = TextTrack(item_id=item.id, lang="zh", source="sidecar")
        s.add(track)
        s.flush()
        lex = Lexeme(simplified="磨坊", is_dict=True)
        s.add(lex)
        s.flush()
        sents = []
        for i, zh in enumerate(["磨坊很旧。", "他去磨坊了。", "磨坊主死了。"]):
            sent = Sentence(
                item_id=item.id, track_id=track.id, ordinal=i, zh=zh,
                t0_ms=i * 1000, t1_ms=i * 1000 + 900, en=f"en{i}",
                analysis={"words": [{"t": "磨坊", "type": "zh", "lex": lex.id}]},
            )
            s.add(sent)
            sents.append(sent)
        s.flush()
        for sent in sents:
            s.add(TokenOccurrence(sentence_id=sent.id, idx=0, item_id=item.id,
                                  surface="磨坊", lexeme_id=lex.id))
        write_fts(s, sents)
        saved = SavedItem(kind="word", lexeme_id=lex.id, surface="磨坊")
        s.add(saved)
        s.flush()
        s.add(SavedContext(saved_item_id=saved.id, sentence_id=sents[0].id,
                           snapshot={"item_id": item.id, "zh": sents[0].zh}))
        s.commit()
        return {"saved_id": saved.id, "lex_id": lex.id,
                "saved_sentence_id": sents[0].id}


def test_queue_enrolls_saved_items_and_prefers_fresh_context(client, seeded):
    q = client.get("/api/review/queue").json()
    assert q["due"] == 1
    (entry,) = q["items"]
    assert entry["saved_item_id"] == seeded["saved_id"]
    assert entry["mode"] == "context"
    # fresh concordance sentence, not the one it was saved from
    assert entry["context"]["sentence_id"] != seeded["saved_sentence_id"]


def test_sentence_items_review_as_listen(client, db_session, seeded):
    # no typed input in review: sentence items are listen-and-reveal cards
    # anchored to their saved context
    with db_session() as s:
        saved = SavedItem(kind="sentence", surface=None)
        s.add(saved)
        s.flush()
        s.add(SavedContext(saved_item_id=saved.id, sentence_id=seeded["saved_sentence_id"],
                           snapshot={"zh": "磨坊很旧。"}))
        s.commit()
        sentence_saved_id = saved.id
    q = client.get("/api/review/queue").json()
    entry = next(e for e in q["items"] if e["saved_item_id"] == sentence_saved_id)
    assert entry["mode"] == "listen"
    assert entry["context"]["sentence_id"] == seeded["saved_sentence_id"]


def test_ladder_pass_fail_and_graduation(client, seeded):
    sid = seeded["saved_id"]
    r = client.post(f"/api/review/{sid}/outcome", json={"result": "pass"}).json()
    assert r["rung"] == 1 and not r["graduated"] and r["next_due_days"] == 3
    r = client.post(f"/api/review/{sid}/outcome", json={"result": "fail"}).json()
    assert r["rung"] == 0 and r["next_due_days"] == 1
    r = client.post(f"/api/review/{sid}/outcome", json={"result": "pass"}).json()
    r = client.post(f"/api/review/{sid}/outcome", json={"result": "pass"}).json()
    assert r["rung"] == 2 and not r["graduated"]  # 3 passes but only just at top
    r = client.post(f"/api/review/{sid}/outcome", json={"result": "pass"}).json()
    assert r["graduated"]  # >=3 passes ending at the top rung -> export tray
    # graduated items leave the queue
    assert client.get("/api/review/queue").json()["due"] == 0


def test_not_due_until_ladder_interval(client, db_session, seeded):
    sid = seeded["saved_id"]
    client.post(f"/api/review/{sid}/outcome", json={"result": "fail"})
    assert client.get("/api/review/queue").json()["due"] == 0  # due tomorrow
    with db_session() as s:
        rs = s.get(ReviewState, sid)
        rs.due_at = datetime.now(timezone.utc) - timedelta(hours=1)
        s.commit()
    assert client.get("/api/review/queue").json()["due"] == 1


def test_search_cjk_and_english(client, seeded):
    r = client.get("/api/search", params={"q": "磨坊主"}).json()
    assert len(r["results"]) == 1
    assert r["results"][0]["zh"] == "磨坊主死了。"
    assert r["results"][0]["t0_ms"] == 2000  # jump target
    r = client.get("/api/search", params={"q": "en1"}).json()
    assert len(r["results"]) == 1
    r = client.get("/api/search", params={"q": "mofang"}).json()
    assert len(r["results"]) == 0  # toneless pinyin is word-spaced: 'mo fang'
    r = client.get("/api/search", params={"q": "mo fang"}).json()
    assert len(r["results"]) == 3


def test_concordance(client, seeded):
    r = client.get(f"/api/lexemes/{seeded['lex_id']}/concordance").json()
    assert len(r["results"]) == 3


def test_dashboard_shape(client, seeded):
    d = client.get("/api/stats/dashboard").json()
    assert d["review_due"] == 1
    assert isinstance(d["weeks"], list)
    assert d["recurring_unknowns"][0]["simplified"] == "磨坊"
