"""Real SQLite regression checks without external models/services or TestClient."""
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta, timezone
import json
from pathlib import Path

import pytest
from fastapi import HTTPException
from sqlalchemy import select, text
from sqlalchemy.orm import sessionmaker
from starlette.requests import Request
from starlette.responses import Response

from app.api import review
from app.api.review import OutcomeIn, review_outcome, review_queue
from app.api.search import _fts_query, _result
from app.api.sentences import get_sentences
from app.db import make_engine
from app.lingua.diff import score_attempt
from app.models import Base, Event, KnowledgeState, Lexeme, MediaItem, MediaRoot, ReviewState, SavedContext, SavedItem, Sense, Sentence, TextTrack
from app.timing import effective_times


@pytest.fixture()
def seeded_db(tmp_path):
    engine = make_engine(tmp_path / "learning.db")
    Base.metadata.create_all(engine)
    with engine.begin() as connection:
        connection.execute(text("CREATE VIRTUAL TABLE sentence_fts USING fts5(zh_words, zh_chars, trad_words, pinyin, en)"))
    factory = sessionmaker(engine, expire_on_commit=False)
    with factory() as session:
        root = MediaRoot(slug="test", kind="video", path=str(tmp_path))
        session.add(root)
        session.flush()
        item = MediaItem(root_id=root.id, relpath="video.mp4", title="Example", kind="video", available=True, ready=True)
        session.add(item)
        session.flush()
        track = TextTrack(item_id=item.id, source="sidecar", lang="zh", offset_ms=500)
        lexeme = Lexeme(simplified="学习", traditional="學習", pinyin="xue2 xi2", is_dict=True)
        session.add_all([track, lexeme])
        session.flush()
        sentence = Sentence(item_id=item.id, track_id=track.id, ordinal=0, zh="学习中文。", t0_ms=1000, t1_ms=2000, analysis={"words": []})
        session.add(sentence)
        session.flush()
        saved = SavedItem(kind="word", lexeme_id=lexeme.id, surface="学习")
        session.add(saved)
        session.flush()
        session.add(SavedContext(saved_item_id=saved.id, sentence_id=sentence.id, snapshot={"zh": sentence.zh, "item_id": item.id}))
        session.add(Sense(lexeme_id=lexeme.id, ord=0, pinyin="xue2 xi2", glosses=["to study", "to learn"]))
        session.execute(text("INSERT INTO sentence_fts VALUES ('学习 中文', '学 习 中 文', '學習 中文', 'xue xi zhong wen', '')"))
        session.commit()
        ids = {"saved": saved.id, "lexeme": lexeme.id, "sentence": sentence.id, "track": track.id, "item": item.id}
    yield factory, ids
    engine.dispose()


def test_shared_dictation_cases():
    cases = json.loads((Path(__file__).parent / "fixtures/dictation_cases.json").read_text())
    for case in cases:
        assert score_attempt(case["expected"], case["typed"]).score == case["score"], case


def test_immediate_duplicate_cannot_graduate_and_request_is_idempotent(seeded_db):
    factory, ids = seeded_db
    with factory() as session:
        first = review_outcome(ids["saved"], OutcomeIn(result="pass", request_uuid="attempt-1"), session)
        assert first["next_due_days"] == 1
        assert not first["graduated"]
        assert review_outcome(ids["saved"], OutcomeIn(result="pass", request_uuid="attempt-1"), session) == first
        with pytest.raises(HTTPException) as error:
            review_outcome(ids["saved"], OutcomeIn(result="pass", request_uuid="attempt-2"), session)
        assert error.value.status_code == 409
        assert session.get(ReviewState, ids["saved"]).passes == 1
        assert session.scalar(select(Event).where(Event.type == "review_outcome")) is not None
        assert session.get(KnowledgeState, ids["lexeme"]) is None


def test_spaced_ladder_requires_initial_practice_then_three_delayed_successes(seeded_db, monkeypatch):
    factory, ids = seeded_db
    now = datetime.now(timezone.utc)
    monkeypatch.setattr(review, "_now", lambda: now)
    for index, days in enumerate([1, 3, 7, 7]):
        with factory() as session:
            result = review_outcome(ids["saved"], OutcomeIn(result="pass", request_uuid=str(index)), session)
            assert result["next_due_days"] == days
            assert result["graduated"] == (index == 3)
        now += timedelta(days=days)
    with factory() as session:
        assert session.get(KnowledgeState, ids["lexeme"]) is None
        from app.models import LearningEvidence
        assert session.query(LearningEvidence).count() == 4
        with pytest.raises(HTTPException):
            review_outcome(ids["saved"], OutcomeIn(result="fail"), session)


def test_two_tabs_claim_one_review(seeded_db):
    factory, ids = seeded_db
    def submit(index):
        with factory() as session:
            try:
                review_outcome(ids["saved"], OutcomeIn(result="pass", request_uuid=f"tab-{index}"), session)
                return 200
            except HTTPException as error:
                return error.status_code
    with ThreadPoolExecutor(max_workers=2) as pool:
        assert sorted(pool.map(submit, [1, 2])) == [200, 409]
    with factory() as session:
        assert session.get(ReviewState, ids["saved"]).passes == 1


def test_review_feedback_and_snapshot_fallback(seeded_db):
    factory, ids = seeded_db
    with factory() as session:
        entry = review_queue(20, session)["items"][0]
        assert entry["answer"]["senses"][0]["defs"] == ["to study", "to learn"]
        assert entry["context"]["t0_ms"] == 1500
        context = session.scalar(select(SavedContext))
        context.sentence_id = None
        session.commit()
        entry = review_queue(20, session)["items"][0]
        assert entry["context"]["zh"] == "学习中文。"
        assert entry["context"]["stream_url"] is None


def test_archived_item_cannot_be_reviewed(seeded_db):
    factory, ids = seeded_db
    with factory() as session:
        session.get(SavedItem, ids["saved"]).archived = True
        session.commit()
        with pytest.raises(HTTPException) as error:
            review_outcome(ids["saved"], OutcomeIn(result="pass"), session)
        assert error.value.status_code == 409


@pytest.mark.parametrize("query", ['hello?', 'xi-an', 'hello OR', '" AND (', '*', '学习', '學習', 'xue2 xi2', 'xué xí'])
def test_search_literals_never_become_fts_syntax(query, seeded_db):
    factory, _ = seeded_db
    with factory() as session:
        match = _fts_query(query)
        if match:
            session.execute(text("SELECT rowid FROM sentence_fts WHERE sentence_fts MATCH :q"), {"q": match}).all()


@pytest.mark.parametrize("query", ["学习", "學習", "xue2 xi2", "xué xí"])
def test_both_scripts_and_spaced_pinyin_match(query, seeded_db):
    factory, _ = seeded_db
    with factory() as session:
        assert session.execute(text("SELECT rowid FROM sentence_fts WHERE sentence_fts MATCH :q"), {"q": _fts_query(query)}).all()


def test_effective_timing_is_shared_and_clamped(seeded_db):
    factory, ids = seeded_db
    with factory() as session:
        sentence = session.get(Sentence, ids["sentence"])
        assert effective_times(session, sentence) == (1500, 2500)
        assert _result(session, sentence)["t0_ms"] == 1500
        session.get(TextTrack, ids["track"]).offset_ms = -1500
        assert effective_times(session, sentence) == (0, 500)


def test_transcript_revision_changes_etag(seeded_db):
    factory, ids = seeded_db
    with factory() as session:
        request = Request({"type": "http", "headers": []})
        first_response = Response()
        get_sentences(ids["item"], request, first_response, session)
        item = session.get(MediaItem, ids["item"])
        item.meta = {"analysis_rev": 1}
        session.commit()
        second_response = Response()
        get_sentences(ids["item"], request, second_response, session)
        assert first_response.headers["etag"] != second_response.headers["etag"]
