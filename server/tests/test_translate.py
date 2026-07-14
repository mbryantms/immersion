"""translate_item: per-batch persistence — a mid-run failure keeps completed
batches, and a retry resumes from the first untranslated sentence."""

from pathlib import Path

import pytest
from sqlalchemy import select
from sqlalchemy.orm import sessionmaker

from app.ai import tasks
from app.ai.tasks import translate_item
from app.db import make_engine
from app.models import AiArtifact, Base, MediaItem, MediaRoot, Sentence, TextTrack


@pytest.fixture()
def db(tmp_path: Path):
    engine = make_engine(tmp_path / "test.db")
    Base.metadata.create_all(engine)
    return sessionmaker(engine, expire_on_commit=False)


@pytest.fixture()
def item_with_sentences(db):
    with db() as s:
        root = MediaRoot(slug="p", kind="podcast", path="/tmp/x")
        s.add(root)
        s.flush()
        item = MediaItem(root_id=root.id, relpath="a.mp3", title="a", kind="audio")
        s.add(item)
        s.flush()
        track = TextTrack(item_id=item.id, lang="zh", source="transcript")
        s.add(track)
        s.flush()
        for i in range(60):  # 3 batches of 25, last partial
            s.add(Sentence(item_id=item.id, track_id=track.id, ordinal=i,
                           zh=f"第{i}句。", t0_ms=0, t1_ms=0))
        s.commit()
        return item.id


def test_batch_checkpoint_survives_failure(db, item_with_sentences, monkeypatch):
    calls = {"n": 0}

    def fake_complete(prompt, timeout_s=600):
        calls["n"] += 1
        if calls["n"] == 2:
            raise RuntimeError("claude -p failed: transient")
        lines = [ln for ln in prompt.splitlines() if ln[:1].isdigit()]
        return [f"en({ln.split('. ', 1)[1]})" for ln in lines]

    monkeypatch.setattr(tasks.provider, "available", lambda: True)
    monkeypatch.setattr(tasks.provider, "complete_json", fake_complete)

    with db() as s:
        with pytest.raises(RuntimeError):
            translate_item(s, item_with_sentences)
    with db() as s:
        done = s.scalars(select(Sentence).where(Sentence.en.is_not(None))).all()
        assert len(done) == 25  # batch 1 committed before batch 2 blew up
        assert all(d.en_source == "ai" for d in done)
        assert s.scalar(select(AiArtifact.id).limit(1)) is not None

    # retry resumes: only the 35 untranslated go out
    with db() as s:
        result = translate_item(s, item_with_sentences)
        assert result["translated"] == 35
    with db() as s:
        assert len(s.scalars(select(Sentence).where(Sentence.en.is_(None))).all()) == 0


def test_count_mismatch_raises(db, item_with_sentences, monkeypatch):
    monkeypatch.setattr(tasks.provider, "available", lambda: True)
    monkeypatch.setattr(tasks.provider, "complete_json", lambda p, timeout_s=600: ["one"])
    with db() as s:
        with pytest.raises(RuntimeError, match="count mismatch"):
            translate_item(s, item_with_sentences)


def test_no_provider_is_a_clean_skip(db, item_with_sentences, monkeypatch):
    monkeypatch.setattr(tasks.provider, "available", lambda: False)
    with db() as s:
        result = translate_item(s, item_with_sentences)
        assert "skipped" in result
