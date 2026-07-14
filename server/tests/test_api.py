"""API tests on a temp database: path security, idempotent saves, idempotent
event replay, knowledge precedence.

The app's get_session dependency is overridden with a throwaway SQLite engine;
TestClient is used without its context manager so the lifespan (which migrates
the real database) never runs."""

from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import sessionmaker

from app.db import get_session, make_engine
from app.main import app
from app.models import (
    AnkiLink,
    Base,
    Event,
    KnowledgeState,
    Lexeme,
    LexemeStats,
    MediaItem,
    MediaRoot,
    ReviewState,
    Sentence,
    TextTrack,
    TokenOccurrence,
)


@pytest.fixture()
def db_session(tmp_path: Path):
    engine = make_engine(tmp_path / "test.db")
    Base.metadata.create_all(engine)
    Session = sessionmaker(engine, expire_on_commit=False)

    def override():
        with Session() as s:
            yield s

    app.dependency_overrides[get_session] = override
    yield Session
    app.dependency_overrides.clear()


@pytest.fixture()
def client(db_session):
    return TestClient(app)  # no context manager: lifespan must not run


@pytest.fixture()
def seeded(db_session, tmp_path: Path):
    """Minimal root + item + sentence + lexeme."""
    with db_session() as s:
        root = MediaRoot(slug="t", kind="video", path=str(tmp_path))
        s.add(root)
        s.flush()
        item = MediaItem(root_id=root.id, relpath="a.mp4", title="a", kind="video", ready=True)
        s.add(item)
        s.flush()
        track = TextTrack(item_id=item.id, lang="zh", source="sidecar", relpath="a.srt")
        s.add(track)
        lex = Lexeme(simplified="你好", traditional="你好", pinyin="ni3 hao3", is_dict=True)
        s.add(lex)
        s.flush()
        sent = Sentence(
            item_id=item.id, track_id=track.id, ordinal=0, zh="你好。", t0_ms=0, t1_ms=1000,
            analysis={"words": [{"t": "你好", "type": "zh", "lex": lex.id}]},
        )
        s.add(sent)
        s.flush()
        s.add(TokenOccurrence(sentence_id=sent.id, idx=0, item_id=item.id, surface="你好", lexeme_id=lex.id))
        s.commit()
        return {"item": item.id, "sentence": sent.id, "lexeme": lex.id}


def test_media_path_traversal_rejected(client, seeded, tmp_path):
    (tmp_path / "secret.txt").write_text("s")
    # raw traversal (starlette may normalize -> 404 route; direct -> 403)
    for path in ("/media/t/../../etc/passwd", "/media/t/%2e%2e/%2e%2e/etc/passwd",
                 "/media/thumbs/../immersion.db"):
        assert client.get(path).status_code in (403, 404)


def test_media_serves_inside_root(client, seeded, tmp_path):
    (tmp_path / "a.mp4").write_bytes(b"fake")
    assert client.get("/media/t/a.mp4").status_code == 200


def test_save_word_idempotent_adds_context(client, seeded):
    body = {"kind": "word", "lexeme_id": seeded["lexeme"], "surface": "你好",
            "sentence_id": seeded["sentence"]}
    first = client.post("/api/saved-items", json=body).json()
    second = client.post("/api/saved-items", json=body).json()
    assert first["created"] is True
    assert second["created"] is False
    assert second["id"] == first["id"]
    items = client.get("/api/saved-items").json()["items"]
    assert len(items) == 1
    assert len(items[0]["contexts"]) == 1  # same sentence twice -> one context
    assert items[0]["contexts"][0]["zh"] == "你好。"  # snapshot captured


def test_event_replay_idempotent(client, seeded):
    ev = {"client_uuid": "abc-123", "type": "lookup",
          "lexeme_id": seeded["lexeme"], "item_id": seeded["item"]}
    assert client.post("/api/events/batch", json=[ev]).json()["inserted"] == 1
    assert client.post("/api/events/batch", json=[ev]).json()["inserted"] == 0
    info = client.get(f"/api/lexemes/{seeded['lexeme']}").json()
    assert info["stats"]["lookups"] == 1  # counter bumped exactly once


def test_knowledge_manual_state(client, seeded):
    r = client.put(f"/api/knowledge/{seeded['lexeme']}", json={"state": "known"}).json()
    assert r["source"] == "manual"
    kn = client.get(f"/api/knowledge?item_id={seeded['item']}").json()
    assert kn["states"][str(seeded["lexeme"])] == "known"
    assert client.put(f"/api/knowledge/{seeded['lexeme']}", json={"state": "bogus"}).status_code == 400


def test_clear_manual_state_reveals_anki_evidence(client, db_session, seeded):
    client.put(f"/api/knowledge/{seeded['lexeme']}", json={"state": "known"})
    with db_session() as session:
        state = session.get(KnowledgeState, seeded["lexeme"])
        state.anki_interval_days = 5
        session.commit()

    result = client.delete(f"/api/knowledge/{seeded['lexeme']}").json()
    assert result == {
        "lexeme_id": seeded["lexeme"], "state": "learning", "source": "anki", "cleared": True,
    }


def test_save_promotes_to_learning_and_clear_manual_returns_to_derived(client, seeded):
    body = {"kind": "word", "lexeme_id": seeded["lexeme"], "surface": "你好",
            "sentence_id": seeded["sentence"]}
    client.post("/api/saved-items", json=body)
    info = client.get(f"/api/lexemes/{seeded['lexeme']}").json()
    assert (info["state"], info["state_source"]) == ("learning", "derived")

    client.put(f"/api/knowledge/{seeded['lexeme']}", json={"state": "known"})
    result = client.put(f"/api/knowledge/{seeded['lexeme']}", json={"state": "new"}).json()
    assert (result["state"], result["source"]) == ("learning", "derived")


def test_reset_exposure_preserves_audit_event(client, db_session, seeded):
    event = {"client_uuid": "lookup-reset", "type": "lookup", "lexeme_id": seeded["lexeme"]}
    client.post("/api/events/batch", json=[event])
    assert client.delete(f"/api/lexemes/{seeded['lexeme']}/stats").json()["reset"] is True
    assert client.get(f"/api/lexemes/{seeded['lexeme']}").json()["stats"]["lookups"] == 0
    with db_session() as session:
        assert session.get(LexemeStats, seeded["lexeme"]) is None
        assert session.query(Event).filter(Event.type == "lexeme_stats_reset").count() == 1


def test_review_reset_and_unsave_cleanup_dependencies(client, db_session, seeded):
    saved_id = client.post("/api/saved-items", json={
        "kind": "word", "lexeme_id": seeded["lexeme"], "surface": "你好",
        "sentence_id": seeded["sentence"],
    }).json()["id"]
    client.post(f"/api/review/{saved_id}/outcome", json={"result": "pass"})
    with db_session() as session:
        session.add(AnkiLink(
            lexeme_id=seeded["lexeme"], saved_item_id=saved_id, note_id=123,
            deck="Test", model="Test", status="exported",
        ))
        session.commit()

    assert client.delete(f"/api/saved-items/{saved_id}/review").json()["reset"] is True
    with db_session() as session:
        assert session.get(ReviewState, saved_id) is None

    assert client.delete(f"/api/saved-items/{saved_id}").status_code == 200
    with db_session() as session:
        link = session.query(AnkiLink).one()
        assert link.saved_item_id is None
        assert session.get(KnowledgeState, seeded["lexeme"]) is None


def test_lookup_span(client, seeded):
    r = client.post("/api/lookup",
                    json={"sentence_id": seeded["sentence"], "start": 0, "end": 2}).json()
    assert r["span"] == "你好"
    assert r["candidates"][0]["simplified"] == "你好"


def test_coverage_reflects_knowledge(client, seeded):
    item = client.get(f"/api/items/{seeded['item']}").json()
    assert item["coverage"] == 0.0
    client.put(f"/api/knowledge/{seeded['lexeme']}", json={"state": "known"})
    item = client.get(f"/api/items/{seeded['item']}").json()
    assert item["coverage"] == 1.0
