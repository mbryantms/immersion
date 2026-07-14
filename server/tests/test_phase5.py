"""Phase 5: whisper segmentation, remux decisions, embedded extraction,
offset application, anki sentence badges, explain caching, rewatch nudge."""

from __future__ import annotations

import shutil
import subprocess
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

from app.ingest.remux import needs_remux
from app.ingest.transcribe import words_to_segments
from app.lingua.convert import zh_norm
from app.models import AnkiSentence, Event, KnowledgeState, MediaItem, PlaybackProgress

from test_api import client, db_session, seeded  # noqa: F401 — fixtures


# ---- whisper word -> sentence segmentation ---------------------------------

def test_segments_split_on_sentence_punct():
    words = [("你好。", 0.0, 0.5), ("我是谁", 0.6, 1.0), ("？", 1.0, 1.1)]
    segs = words_to_segments(words)
    assert [s.text for s in segs] == ["你好。", "我是谁？"]
    assert segs[0].t0_ms == 0 and segs[0].t1_ms == 500


def test_segments_split_on_silence_gap():
    words = [("第一句", 0.0, 1.0), ("第二句", 3.0, 4.0)]  # 2s gap, no punctuation
    segs = words_to_segments(words)
    assert [s.text for s in segs] == ["第一句", "第二句"]


def test_segments_latin_words_keep_spaces():
    words = [("我们", 0.0, 0.4), ("用", 0.4, 0.6), ("GPS", 0.6, 1.0), ("导航", 1.0, 1.4), ("。", 1.4, 1.5)]
    segs = words_to_segments(words)
    assert segs[0].text == "我们用GPS导航。"
    words = [("hello", 0.0, 0.4), ("world", 0.5, 0.9), ("。", 0.9, 1.0)]
    assert words_to_segments(words)[0].text == "hello world。"


def test_segments_runaway_length_flushes():
    words = [(f"字{i}" * 10, i * 1.0, i * 1.0 + 0.9) for i in range(10)]  # no punct, no gaps
    segs = words_to_segments(words)
    assert len(segs) > 1


# ---- remux decision ---------------------------------------------------------

def _item(relpath: str, vcodec: str | None, acodec: str | None = "aac", kind: str = "video"):
    return MediaItem(
        root_id=1, relpath=relpath, title="x", kind=kind,
        vcodec=vcodec, acodec=acodec, available=True,
    )


def test_needs_remux_matrix():
    assert not needs_remux(_item("a.mp4", "h264"))
    assert not needs_remux(_item("a.webm", "vp9", "opus"))
    assert needs_remux(_item("a.mkv", "h264"))          # container rewrap
    assert needs_remux(_item("a.mp4", "hevc"))          # codec transcode
    assert needs_remux(_item("a.mp4", "h264", "ac3"))   # audio transcode
    assert not needs_remux(_item("a.mkv", "h264", kind="audio"))
    assert not needs_remux(_item("a.mkv", None))        # unprobed: wait for scan


# ---- zh normalization -------------------------------------------------------

def test_zh_norm_strips_html_and_whitespace():
    assert zh_norm('<b>你好</b> 世界&nbsp;。\n') == "你好世界。"


# ---- sentences payload: offset + anki badge ---------------------------------

def test_offset_applied_to_sentences(client, db_session, seeded):  # noqa: F811
    from app.models import TextTrack

    with db_session() as s:
        track_id = s.query(TextTrack).first().id
    r = client.patch(f"/api/tracks/{track_id}", json={"offset_ms": 500})
    assert r.json()["offset_ms"] == 500
    r = client.get(f"/api/items/{seeded['item']}/sentences")
    sent = r.json()["sentences"][0]
    assert (sent["t0"], sent["t1"]) == (500, 1500)
    # negative offsets clamp at zero rather than going back in time
    client.patch(f"/api/tracks/{track_id}", json={"offset_ms": -500})
    sent = client.get(f"/api/items/{seeded['item']}/sentences").json()["sentences"][0]
    assert (sent["t0"], sent["t1"]) == (0, 500)


def test_anki_badge_matches_normalized_zh(client, db_session, seeded):  # noqa: F811
    with db_session() as s:
        s.add(AnkiSentence(note_id=1, zh_norm=zh_norm("你好。"), imported_at=datetime.now(timezone.utc)))
        s.commit()
    sent = client.get(f"/api/items/{seeded['item']}/sentences").json()["sentences"][0]
    assert sent["anki"] is True


# ---- explain: cached per zh text, provenance travels -------------------------

def test_explain_caches_by_input_hash(client, db_session, seeded, monkeypatch):  # noqa: F811
    from app.ai import provider

    calls = {"n": 0}

    def fake_complete(prompt: str, timeout_s: int = 0):
        calls["n"] += 1
        assert "你好" in prompt  # grounded on the app's tokenization
        return {
            "natural": "Hello.", "literal": "hello", "structure": "greeting",
            "words": [{"zh": "你好", "role": "greeting"}],
            "particles": [], "pronunciation": [], "nuance": "",
            "variations": [{"zh": "您好", "note": "formal"}],
            "pattern": {"name": "greeting", "examples": [{"zh": "你好吗", "en": "How are you?"}]},
            "mistakes": [],
        }

    monkeypatch.setattr(provider, "available", lambda: True)
    monkeypatch.setattr(provider, "complete_json", fake_complete)

    first = client.post(f"/api/sentences/{seeded['sentence']}/explain")
    assert first.status_code == 200
    body = first.json()
    assert body["natural"] == "Hello."
    assert body["model"]
    assert body["pinyin"]  # derived from analysis, not the AI
    assert "level" in body["hsk"]
    assert body["pattern"]["examples"][0]["py"].startswith("nǐ")  # deterministic pinyin attached
    assert body["variations"][0]["py"]
    second = client.post(f"/api/sentences/{seeded['sentence']}/explain")
    assert second.status_code == 200
    assert calls["n"] == 1  # second hit served from ai_artifact


def test_explain_unavailable_is_503(client, seeded, monkeypatch):  # noqa: F811
    from app.ai import provider

    monkeypatch.setattr(provider, "available", lambda: False)
    assert client.post(f"/api/sentences/{seeded['sentence']}/explain").status_code == 503


# ---- rewatch nudge ----------------------------------------------------------

def _make_mastered(db_session, seeded):  # noqa: F811
    with db_session() as s:
        s.merge(KnowledgeState(lexeme_id=seeded["lexeme"], state="known", source="manual"))
        s.merge(PlaybackProgress(item_id=seeded["item"], position_ms=1000, completed=True))
        s.commit()


def test_rewatch_nudge_on_mastered_completed_item(client, db_session, seeded):  # noqa: F811
    assert client.get(f"/api/items/{seeded['item']}").json()["rewatch_nudge"] is False
    _make_mastered(db_session, seeded)
    assert client.get(f"/api/items/{seeded['item']}").json()["rewatch_nudge"] is True


def test_rewatch_nudge_suppressed_by_recent_lookups(client, db_session, seeded):  # noqa: F811
    _make_mastered(db_session, seeded)
    with db_session() as s:
        for i in range(5):
            s.add(Event(
                type="lookup", item_id=seeded["item"], lexeme_id=seeded["lexeme"],
                ts=datetime.now(timezone.utc) - timedelta(days=1), client_uuid=f"uuid-{i}",
            ))
        s.commit()
    assert client.get(f"/api/items/{seeded['item']}").json()["rewatch_nudge"] is False


# ---- transcribe endpoint ----------------------------------------------------

def test_transcribe_endpoint_queues_job(client, db_session, seeded):  # noqa: F811
    from app.models import Job

    r = client.post(f"/api/items/{seeded['item']}/transcribe")
    assert r.json()["queued"] is True
    with db_session() as s:
        job = s.query(Job).filter_by(type="whisper_transcribe").one()
        assert job.payload == {"item_id": seeded["item"]}
    # duplicate queue attempt dedupes
    assert client.post(f"/api/items/{seeded['item']}/transcribe").json()["queued"] is False


# ---- anki sentence import (mocked AnkiConnect) -------------------------------

def test_import_sentence_cards_replaces_cache(db_session, seeded, monkeypatch):  # noqa: F811
    from app.anki import import_known as mod
    from app.models import Setting

    with db_session() as s:
        s.merge(Setting(key="anki_sentence_search", value={"query": "deck:LFC", "field": "Sentence"}))
        s.add(AnkiSentence(note_id=99, zh_norm="旧句子", imported_at=datetime.now(timezone.utc)))
        s.commit()

    def fake_ac(action, **params):
        if action == "findNotes":
            return [11, 12]
        if action == "notesInfo":
            return [
                {"noteId": 11, "fields": {"Sentence": {"value": "<b>你好。</b>"}}},
                {"noteId": 12, "fields": {"Sentence": {"value": "很 好。"}}},
            ]
        raise AssertionError(action)

    monkeypatch.setattr(mod, "ac", fake_ac)
    with db_session() as s:
        n = mod.import_sentence_cards(s)
        assert n == 2
        rows = {r.zh_norm for r in s.query(AnkiSentence)}
        assert rows == {"你好。", "很好。"}  # stale row replaced


# ---- embedded extraction (real ffmpeg, tiny generated mkv) -------------------

@pytest.mark.skipif(shutil.which("ffmpeg") is None, reason="ffmpeg not installed")
def test_embedded_zh_stream_extracted(db_session, seeded, tmp_path, monkeypatch):  # noqa: F811
    from app.ingest.embedded import ensure_embedded_tracks

    srt = tmp_path / "in.srt"
    srt.write_text("1\n00:00:00,000 --> 00:00:01,000\n你好，世界。\n", encoding="utf-8")
    mkv = tmp_path / "a.mkv"
    subprocess.run(
        ["ffmpeg", "-loglevel", "error",
         "-f", "lavfi", "-i", "color=black:s=64x64:d=1",
         "-i", str(srt), "-map", "0:v", "-map", "1:s",
         "-c:v", "libx264", "-c:s", "srt", "-y", str(mkv)],
        check=True,
    )
    monkeypatch.setattr("app.ingest.embedded.settings.data_dir", tmp_path, raising=False)
    monkeypatch.setattr(
        "app.config.Settings.subs_dir",
        property(lambda self: tmp_path / "subs"),
    )

    with db_session() as s:
        item = s.get(MediaItem, seeded["item"])
        # simulate the scanner's probe: one untagged srt stream at index 1
        item.meta = {"embedded_subs": [{"index": 1, "codec": "subrip", "lang": None}]}
        # deselect the seeded zh sidecar so the embedded stream is wanted
        from app.models import TextTrack

        for t in s.query(TextTrack).filter_by(item_id=item.id):
            t.selected = False
        s.flush()

        tracks = ensure_embedded_tracks(s, item, mkv)
        assert len(tracks) == 1
        assert tracks[0].lang == "zh" and tracks[0].source == "embedded"
        assert (tmp_path / "subs" / f"{item.id}.1.srt").exists()
        assert (item.meta or {}).get("embedded_checked") == item.fingerprint
