"""Anki export: field building, dup surfacing, per-note links, idempotency —
all against a mocked AnkiConnect."""

from pathlib import Path

import pytest
from sqlalchemy import select
from sqlalchemy.orm import sessionmaker

from app.anki import export
from app.anki.connect import AnkiError
from app.db import make_engine
from app.models import (
    AnkiLink,
    Base,
    Lexeme,
    MediaItem,
    MediaRoot,
    SavedContext,
    SavedItem,
    Sentence,
    TextTrack,
)


class FakeAnki:
    def __init__(self, dups=None):
        self.calls = []
        self.dups = dups or {}
        self.next_note_id = 1000

    def __call__(self, action, **params):
        self.calls.append((action, params))
        if action == "findNotes":
            word = params["query"].split(":", 1)[1].strip('"')
            return self.dups.get(word, [])
        if action == "notesInfo":
            return [{"fields": {"Meaning": {"value": "existing meaning"}}} for _ in params["notes"]]
        if action == "modelFieldNames":
            return ["ID", "Simplified", "Traditional", "Pinyin", "Meaning", "Audio",
                    "Sentence", "SentenceTraditional", "SentencePinyin",
                    "SentenceMeaning", "SentenceAudio"]
        if action == "createDeck":
            return 1
        if action == "storeMediaFile":
            return params["filename"]
        if action == "addNote":
            fields = params["note"]["fields"]
            if (self.dups.get(fields["Simplified"])
                    and not params["note"]["options"]["allowDuplicate"]):
                raise AnkiError("cannot create note because it is a duplicate")
            self.next_note_id += 1
            return self.next_note_id
        raise AssertionError(f"unexpected action {action}")


@pytest.fixture()
def db(tmp_path: Path):
    engine = make_engine(tmp_path / "test.db")
    Base.metadata.create_all(engine)
    return sessionmaker(engine, expire_on_commit=False)


@pytest.fixture()
def seeded(db):
    with db() as s:
        root = MediaRoot(slug="lfc", kind="video", path="/tmp/nowhere")
        s.add(root)
        s.flush()
        item = MediaItem(root_id=root.id, relpath="a.mp4", title="ep", kind="video",
                         available=True)
        s.add(item)
        s.flush()
        track = TextTrack(item_id=item.id, lang="zh", source="sidecar")
        s.add(track)
        s.flush()
        sent = Sentence(item_id=item.id, track_id=track.id, ordinal=0,
                        zh="磨坊主死了。", en="The miller died.", t0_ms=1000, t1_ms=3000)
        s.add(sent)
        lex = Lexeme(simplified="磨坊", traditional="磨坊", pinyin="mo4 fang2", is_dict=True)
        s.add(lex)
        s.flush()
        saved = SavedItem(kind="word", lexeme_id=lex.id, surface="磨坊")
        s.add(saved)
        s.flush()
        s.add(SavedContext(saved_item_id=saved.id, sentence_id=sent.id,
                           snapshot={"item_id": item.id, "zh": sent.zh, "en": sent.en,
                                     "t0_ms": 1000, "t1_ms": 3000}))
        s.commit()
        return saved.id


def test_preview_fields_and_dups(db, seeded, monkeypatch):
    fake = FakeAnki(dups={"磨坊": [11, 12]})
    monkeypatch.setattr(export, "ac", fake)
    with db() as s:
        preview = export.build_preview(s, [seeded])
    (p,) = preview["items"]
    assert preview["deck"] == "Mined::Immersion"
    assert p["fields"]["ID"] == "磨坊mofang"  # deck convention: word + toneless pinyin
    assert p["fields"]["Simplified"] == "磨坊"
    assert p["fields"]["Sentence"] == "磨坊主死了。"
    assert p["fields"]["SentenceMeaning"] == "The miller died."
    assert p["fields"]["Pinyin"]  # tone marks generated
    assert p["duplicates"] == 2
    assert p["duplicate_meanings"] == ["existing meaning", "existing meaning"]
    assert p["can_clip"] and p["can_image"]
    assert p["already_exported"] is None


def test_export_adds_note_and_link(db, seeded, monkeypatch):
    fake = FakeAnki()
    monkeypatch.setattr(export, "ac", fake)
    with db() as s:
        result = export.export_items(
            s,
            [{"saved_item_id": seeded,
              "fields": {"Simplified": "磨坊", "Meaning": "edited meaning", "Bogus": "x"},
              "include_media": False}],
        )
    assert result["added"] == 1
    added = [c for c in fake.calls if c[0] == "addNote"]
    note = added[0][1]["note"]
    assert note["deckName"] == "Mined::Immersion"
    assert note["tags"] == ["immersion-app"]
    assert note["fields"]["Meaning"] == "edited meaning"
    assert "Bogus" not in note["fields"]  # unknown fields dropped via modelFieldNames
    with db() as s:
        link = s.scalars(select(AnkiLink)).one()
        assert link.saved_item_id == seeded and link.note_id == 1001


def test_reexport_is_skipped(db, seeded, monkeypatch):
    fake = FakeAnki()
    monkeypatch.setattr(export, "ac", fake)
    entry = {"saved_item_id": seeded, "fields": {"Simplified": "磨坊"}, "include_media": False}
    with db() as s:
        export.export_items(s, [entry])
        result = export.export_items(s, [entry])
    assert result["added"] == 0
    assert result["results"][0]["status"] == "already_exported"
    with db() as s:
        assert len(s.scalars(select(AnkiLink)).all()) == 1


def test_duplicate_blocked_unless_allowed(db, seeded, monkeypatch):
    fake = FakeAnki(dups={"磨坊": [11]})
    monkeypatch.setattr(export, "ac", fake)
    entry = {"saved_item_id": seeded, "fields": {"Simplified": "磨坊"}, "include_media": False}
    with db() as s:
        result = export.export_items(s, [entry])
        assert result["results"][0]["status"] == "error"
        assert "duplicate" in result["results"][0]["error"]
        result = export.export_items(s, [{**entry, "allow_duplicate": True}])
        assert result["results"][0]["status"] == "added"
