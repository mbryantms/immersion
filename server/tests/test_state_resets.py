"""State/reset contracts without the environment-sensitive TestClient harness."""

from sqlalchemy.orm import sessionmaker

from app.api.knowledge import StateIn, clear_knowledge, put_knowledge, reset_lexeme_stats
from app.api.events import EventIn, post_events
from app.api.review import OutcomeIn, review_outcome
from app.api.saved import SaveIn, delete_saved, reset_saved_review, reset_sentence_played, save_item
from app.db import make_engine
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


def _seed(tmp_path):
    engine = make_engine(tmp_path / "state-resets.db")
    Base.metadata.create_all(engine)
    Session = sessionmaker(engine, expire_on_commit=False)
    with Session() as session:
        root = MediaRoot(slug="test", kind="video", path=str(tmp_path))
        session.add(root)
        session.flush()
        item = MediaItem(root_id=root.id, relpath="test.mp4", title="Test", kind="video", ready=True)
        session.add(item)
        session.flush()
        track = TextTrack(item_id=item.id, lang="zh", source="sidecar", relpath="test.srt")
        lexeme = Lexeme(simplified="你好", traditional="你好", pinyin="ni3 hao3", is_dict=True)
        session.add_all([track, lexeme])
        session.flush()
        sentence = Sentence(
            item_id=item.id, track_id=track.id, ordinal=0, zh="你好。", t0_ms=0, t1_ms=1000,
            analysis={"words": [{"t": "你好", "type": "zh", "lex": lexeme.id}]},
        )
        session.add(sentence)
        session.flush()
        session.add(TokenOccurrence(
            sentence_id=sentence.id, idx=0, item_id=item.id, surface="你好", lexeme_id=lexeme.id,
        ))
        session.commit()
        return Session, lexeme.id, sentence.id


def test_word_and_review_reset_flow(tmp_path):
    Session, lexeme_id, sentence_id = _seed(tmp_path)
    with Session() as session:
        saved_id = save_item(SaveIn(
            kind="word", lexeme_id=lexeme_id, surface="你好", sentence_id=sentence_id,
        ), session)["id"]
        state = session.get(KnowledgeState, lexeme_id)
        assert (state.state, state.source) == ("learning", "derived")

        put_knowledge(lexeme_id, StateIn(state="known"), session)
        result = put_knowledge(lexeme_id, StateIn(state="new"), session)
        assert (result["state"], result["source"]) == ("learning", "derived")

        item_id = session.get(Sentence, sentence_id).item_id
        post_events([
            EventIn(client_uuid="play-before-reset", type="sentence_played", item_id=item_id, sentence_id=sentence_id),
        ], session)
        stats = session.get(LexemeStats, lexeme_id)
        stats.encounters = 4
        stats.lookups = 2
        session.commit()
        assert reset_lexeme_stats(lexeme_id, session)["reset"] is True
        assert session.get(LexemeStats, lexeme_id) is None
        assert session.query(Event).filter(Event.type == "lexeme_stats_reset").count() == 1

        post_events([
            EventIn(client_uuid="play-one", type="sentence_played", item_id=item_id, sentence_id=sentence_id),
            EventIn(client_uuid="play-two", type="sentence_played", item_id=item_id, sentence_id=sentence_id),
        ], session)
        stats = session.get(LexemeStats, lexeme_id)
        assert (stats.encounters, stats.distinct_items) == (2, 1)
        assert reset_sentence_played(sentence_id, session)["played"] is False
        latest = session.query(Event).order_by(Event.id.desc()).first()
        assert (latest.type, latest.sentence_id) == ("sentence_play_reset", sentence_id)
        # Marking a sentence unplayed is presentation state, not a rewrite of
        # word exposure or prior sentence-play events.
        assert session.get(LexemeStats, lexeme_id).encounters == 2

        review_outcome(saved_id, OutcomeIn(result="pass"), session)
        assert session.get(ReviewState, saved_id) is not None
        assert reset_saved_review(saved_id, session)["reset"] is True
        assert session.get(ReviewState, saved_id) is None

        session.add(AnkiLink(
            lexeme_id=lexeme_id, saved_item_id=saved_id, note_id=123,
            deck="Test", model="Test", status="exported",
        ))
        session.commit()
        delete_saved(saved_id, session)
        link = session.query(AnkiLink).one()
        assert link.saved_item_id is None
        assert session.get(KnowledgeState, lexeme_id) is None


def test_clear_manual_state_restores_anki(tmp_path):
    Session, lexeme_id, _ = _seed(tmp_path)
    with Session() as session:
        put_knowledge(lexeme_id, StateIn(state="ignored"), session)
        state = session.get(KnowledgeState, lexeme_id)
        state.anki_interval_days = 30
        session.commit()

        result = clear_knowledge(lexeme_id, session)
        assert (result["state"], result["source"], result["cleared"]) == ("known", "anki", True)
