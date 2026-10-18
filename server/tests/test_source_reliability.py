# ruff: noqa: F811
"""Persistent corrections, identities, media recovery, and source-quality checks."""

from pathlib import Path
import subprocess
import pytest
from sqlalchemy import select, text

from app.models import (
    Sentence,
    SentenceIdentity,
    SentenceCorrection,
    MediaItem,
    TextTrack,
    SavedContext,
    Event,
    Job,
    SavedItem,
)
from app.ingest.analysis import write_sentences
from app.ingest.subtitles import Segment, Cue
from app.ingest.align_tracks import assign_en
from app.ingest.remux import remux_current, needs_remux
from test_api import client, db_session, seeded  # noqa: F401


@pytest.fixture(autouse=True)
def dictionary(tmp_path, monkeypatch):
    from app.lingua import cedict
    from app.ingest import analysis

    path = tmp_path / "dictionary.txt"
    path.write_text(
        "你好 你好 [ni3 hao3] /hello/\n學習 学习 [xue2 xi2] /study/\n銀行 银行 [yin2 hang2] /bank/\n"
    )
    data = cedict.Cedict(path)
    monkeypatch.setattr(cedict, "load", lambda: data)
    monkeypatch.setattr(analysis, "load_cedict", lambda: data)
    monkeypatch.setattr(analysis, "hsk_levels", lambda: {})


@pytest.fixture()
def indexed(db_session, seeded):
    with db_session() as session:
        session.execute(
            text(
                "CREATE VIRTUAL TABLE sentence_fts USING fts5(zh_words, zh_chars, trad_words, pinyin, en)"
            )
        )
        session.commit()
    return seeded


def test_correct_reset_restore_conflict_and_source_provenance(client, db_session, indexed):
    sid = indexed["sentence"]
    endpoint = f"/api/sentences/{sid}/corrections"
    original = client.get(endpoint).json()
    result = client.patch(
        endpoint,
        json={
            "expected_revision": 0,
            "en": "Hello here",
            "t0_ms": 250,
            "t1_ms": 1250,
            "words": [{"start": 0, "reading": "ni2 hao3", "meaning": "greeting in this scene"}],
        },
    )
    assert result.status_code == 200, result.text
    saved = result.json()
    assert saved["revision"] == 1
    assert saved["source"]["en"] is None
    assert saved["current"]["words"][0]["reading"] == "ni2 hao3"
    assert (
        client.patch(endpoint, json={"expected_revision": 0, "en": "stale edit"}).status_code == 409
    )
    transcript = client.get(f"/api/items/{indexed['item']}/sentences").json()["sentences"][0]
    assert transcript["provenance"]["timing_source"] == "corrected"
    assert transcript["provenance"]["translation_source"] == "user"
    assert client.get("/api/search?q=Hello").json()["results"]
    reset = client.patch(endpoint, json={"expected_revision": 1, "reset": True}).json()
    assert (
        reset["current"]["en"] is None and reset["current"]["t0_ms"] == original["source"]["t0_ms"]
    )
    restored = client.patch(endpoint, json={"expected_revision": 2, "restore_revision": 1}).json()
    assert restored["current"]["en"] == "Hello here"
    with db_session() as session:
        assert len(session.scalars(select(SentenceCorrection)).all()) == 3


def test_text_correction_is_local_and_export_uses_corrected_text(
    client, indexed, db_session, monkeypatch
):
    from app.lingua import pipeline
    from app.anki.export import _fields

    monkeypatch.setattr(
        pipeline, "tokenize", lambda _: pytest.fail("API imported the heavy tokenizer")
    )
    saved = client.post(
        "/api/saved-items", json={"kind": "sentence", "sentence_id": indexed["sentence"]}
    ).json()["id"]
    result = client.patch(
        f"/api/sentences/{indexed['sentence']}/corrections",
        json={"expected_revision": 0, "zh": "學習 Nathan。", "en": "Study Nathan."},
    )
    assert result.status_code == 200, result.text
    assert result.json()["source"]["zh"] == "你好。"
    assert "".join(w["t"] for w in result.json()["current"]["words"]) == "學習 Nathan。"
    with db_session() as session:
        fields, _ = _fields(session, session.get(SavedItem, saved))
        assert fields["Sentence"] == fields["Simplified"] == "學習 Nathan。"
    assert client.get("/api/search?q=学习").json()["results"]


def test_invalid_correction_rolls_back(client, indexed):
    endpoint = f"/api/sentences/{indexed['sentence']}/corrections"
    for edits in (
        {"t0_ms": 2000},
        {"zh": "   "},
        {"words": [{"start": 9, "reading": "ni3"}]},
        {"reset": True, "en": "oops"},
    ):
        result = client.patch(endpoint, json={"expected_revision": 0, **edits})
        assert result.status_code == 400, result.text
        assert client.get(endpoint).json()["revision"] == 0


def install_analysis(monkeypatch):
    from app.ingest import analysis

    monkeypatch.setattr(
        analysis,
        "analyze_sentences",
        lambda sentences, **_: [[{"t": sentence, "type": "x"}] for sentence in sentences],
    )


def ingest(session, item_id, segments):
    item = session.get(MediaItem, item_id)
    track = session.scalar(select(TextTrack).where(TextTrack.item_id == item_id))
    write_sentences(session, item, track, segments, None)
    session.commit()
    return session.scalars(
        select(Sentence).where(Sentence.item_id == item_id).order_by(Sentence.ordinal)
    ).all()


def test_repeated_lines_keep_identity_and_correction_after_reingest(
    client, indexed, db_session, monkeypatch
):
    install_analysis(monkeypatch)
    with db_session() as session:
        initial = ingest(
            session, indexed["item"], [Segment(1000, 2000, "重复。"), Segment(6000, 7000, "重复。")]
        )
        ids = [sentence.id for sentence in initial]
    assert (
        client.patch(
            f"/api/sentences/{ids[1]}/corrections",
            json={"expected_revision": 0, "en": "second occurrence"},
        ).status_code
        == 200
    )
    saved = client.post(
        "/api/saved-items", json={"kind": "sentence", "sentence_id": ids[1]}
    ).json()["id"]
    with db_session() as session:
        again = ingest(
            session, indexed["item"], [Segment(1100, 2100, "重复。"), Segment(6100, 7100, "重复。")]
        )
        assert [sentence.id for sentence in again] == ids
        assert again[0].en is None and again[1].en == "second occurrence"
        context = session.scalar(select(SavedContext).where(SavedContext.saved_item_id == saved))
        assert context.sentence_id == ids[1]


def test_removed_ids_never_attach_old_events_to_new_text(indexed, db_session, monkeypatch):
    install_analysis(monkeypatch)
    with db_session() as session:
        original = indexed["sentence"]
        session.add(Event(type="sentence_played", sentence_id=original, item_id=indexed["item"]))
        session.commit()
        current = ingest(session, indexed["item"], [Segment(1000, 2000, "全新的话。")])
        assert current[0].id > original
        assert session.get(Sentence, original) is None
        assert session.get(SentenceIdentity, original).source["zh"] == "你好。"
        assert session.scalar(select(Event)).sentence_id == original


def test_removed_source_can_recover_its_identity(indexed, db_session, monkeypatch):
    install_analysis(monkeypatch)
    with db_session() as session:
        first = ingest(session, indexed["item"], [Segment(0, 1000, "第一句。")])[0].id
        ingest(session, indexed["item"], [Segment(0, 1000, "另一句。")])
        assert ingest(session, indexed["item"], [Segment(0, 1000, "第一句。")])[0].id == first


def test_temporal_coverage_counts_union_not_sum():
    result = assign_en(
        [Segment(0, 4000, "你好。")], [Cue(0, 2000, "One."), Cue(0, 2000, "Another.")]
    )
    assert result[0][1] == 0.5


def test_deleted_sidecar_deselected_and_choice_retained(indexed, db_session, tmp_path):
    from app.ingest.scanner import _sync_tracks
    from app.models import MediaRoot

    with db_session() as session:
        item = session.get(MediaItem, indexed["item"])
        root = session.get(MediaRoot, item.root_id)
        track = session.scalar(select(TextTrack).where(TextTrack.item_id == item.id))
        item.meta = {"track_choices": {"zh": track.id}}
        _sync_tracks(session, root, item, Path(root.path) / item.relpath)
        assert track.selected is False and track.meta["available"] is False
        assert item.meta["track_choices"]["zh"] == track.id


def test_track_selection_survives_rescan_and_rejects_wrong_language(client, indexed, db_session):
    with db_session() as session:
        another = TextTrack(
            item_id=indexed["item"], lang="zh", source="sidecar", relpath="alt.zh.srt"
        )
        english = TextTrack(
            item_id=indexed["item"], lang="en", source="sidecar", relpath="alt.en.srt"
        )
        session.add_all([another, english])
        session.commit()
        chosen, wrong = another.id, english.id
    response = client.post(f"/api/items/{indexed['item']}/tracks", json={"zh_track_id": chosen})
    assert response.status_code == 200
    assert client.get(f"/api/items/{indexed['item']}").json()["active_tracks"]["zh"] == chosen
    assert (
        client.post(f"/api/items/{indexed['item']}/tracks", json={"zh_track_id": wrong}).status_code
        == 400
    )


def test_embedded_cache_contains_source_fingerprint(tmp_path, monkeypatch):
    from app.ingest.embedded import sub_path

    assert sub_path(1, 2, "a") != sub_path(1, 2, "b")


def test_remux_cache_requires_nonempty_current_file(indexed, db_session, tmp_path, monkeypatch):
    from app.config import settings

    monkeypatch.setattr(type(settings), "remux_dir", property(lambda _: tmp_path / "remux"))
    with db_session() as session:
        item = session.get(MediaItem, indexed["item"])
        item.fingerprint = "new"
        item.meta = {"remux": {"fp": "new"}}
        assert not remux_current(item)
        (tmp_path / "remux").mkdir()
        output = tmp_path / "remux" / f"{item.id}.mp4"
        output.write_bytes(b"")
        assert not remux_current(item)
        output.write_bytes(b"video")
        assert remux_current(item)
        item.fingerprint = "changed"
        assert not remux_current(item)


def test_failed_audio_conversion_preserves_previous_cache(
    indexed, db_session, tmp_path, monkeypatch
):
    from app.config import settings
    from app.ingest.podcast import transcode_m4a

    monkeypatch.setattr(type(settings), "audio_dir", property(lambda _: tmp_path / "audio"))
    with db_session() as session:
        item = session.get(MediaItem, indexed["item"])
        item.fingerprint = "new"
        item.meta = {"m4a_fp": "old"}
        (tmp_path / "audio").mkdir()
        output = tmp_path / "audio" / f"{item.id}.m4a"
        output.write_bytes(b"valid old cache")

        def fail(*args, **kwargs):
            Path(args[0][-1]).write_bytes(b"partial")
            raise subprocess.CalledProcessError(1, args[0])

        monkeypatch.setattr(subprocess, "run", fail)
        with pytest.raises(subprocess.CalledProcessError):
            transcode_m4a(tmp_path / "source.mp3", item)
        assert output.read_bytes() == b"valid old cache"
        assert not output.with_suffix(".part.m4a").exists()


@pytest.mark.parametrize(
    "extension,video,audio,expected",
    [
        (".webm", "h264", "aac", True),
        (".mp4", "h264", "aac", False),
        (".webm", "vp9", "opus", False),
        (".mp4", "h264", "dts", True),
    ],
)
def test_codec_and_container_combinations(extension, video, audio, expected):
    assert (
        needs_remux(
            MediaItem(
                kind="video", available=True, relpath="file" + extension, vcodec=video, acodec=audio
            )
        )
        is expected
    )


def test_dynamic_root_range_serving_and_reserved_slugs(client, indexed, tmp_path):
    (tmp_path / "a.mp4").write_bytes(b"0123456789")
    response = client.get("/media/t/a.mp4", headers={"Range": "bytes=2-4"})
    assert response.status_code == 206 and response.content == b"234"
    for slug in ("remux", "thumbs", "audio", "", "../a"):
        assert (
            client.post("/api/roots", json={"slug": slug, "path": str(tmp_path)}).status_code == 400
        )


def test_repair_job_is_queued_without_reanalyzing_learning_history(client, indexed, db_session):
    assert client.post(f"/api/items/{indexed['item']}/repair-media").status_code == 200
    with db_session() as session:
        assert session.scalar(select(Job)).type == "repair_media"
        assert session.get(Sentence, indexed["sentence"]).zh == "你好。"


def test_episode_matching_does_not_pair_dates_by_first_year():
    from app.ingest.podcast import episode_number

    assert episode_number("2026-10-18 transcript") is None
    assert episode_number("2026-10-19 audio") is None
    assert episode_number("episode-42-transcript") == episode_number("第42集普通话") == 42


def test_corrected_chinese_survives_reingestion_and_reset(client, indexed, db_session, monkeypatch):
    endpoint = f"/api/sentences/{indexed['sentence']}/corrections"
    assert client.patch(endpoint, json={"expected_revision": 0, "zh": "學習。"}).status_code == 200
    install_analysis(monkeypatch)
    with db_session() as session:
        rows = ingest(session, indexed["item"], [Segment(0, 1000, "你好。")])
        assert rows[0].id == indexed["sentence"]
        assert rows[0].zh == "學習。"
    current = client.get(endpoint).json()
    response = client.patch(
        endpoint, json={"expected_revision": current["revision"], "reset": True}
    )
    assert response.json()["current"]["zh"] == "你好。"


def test_alignment_metadata_flags_interpolated_sentences():
    from app.lingua.align import sentence_times

    _, quality = sentence_times(
        ["你好。", "完全没有匹配。"], [("你好", 0.0, 1.0)], with_quality=True
    )
    assert quality[0]["matched_fraction"] == 1
    assert not quality[0]["interpolated"]
    assert quality[1]["matched_fraction"] == 0
    assert quality[1]["interpolated"]


def test_superseded_media_revision_is_not_served(
    client, indexed, db_session, tmp_path, monkeypatch
):
    from app.config import settings

    monkeypatch.setattr(type(settings), "remux_dir", property(lambda _: tmp_path / "remux"))
    (tmp_path / "remux").mkdir()
    (tmp_path / "remux" / f"{indexed['item']}.mp4").write_bytes(b"cached video")
    with db_session() as session:
        item = session.get(MediaItem, indexed["item"])
        item.fingerprint = "source-new"
        item.meta = {"remux": {"fp": "source-new", "revision": "cache-new"}}
        session.commit()
    assert client.get(f"/media/remux/{indexed['item']}.mp4?v=cache-old").status_code == 409
    assert client.get(f"/media/remux/{indexed['item']}.mp4?v=cache-new").status_code == 200


def test_srt_podcast_keeps_source_timing(indexed, db_session, monkeypatch):
    from app.ingest import podcast
    from app.models import MediaRoot

    captured = []
    monkeypatch.setattr(podcast, "transcode_m4a", lambda *args: None)
    monkeypatch.setattr(podcast, "make_cover_thumb", lambda *args: None)
    monkeypatch.setattr(
        podcast,
        "write_sentences",
        lambda session, item, track, segments, en: captured.extend(segments),
    )
    with db_session() as session:
        item = session.get(MediaItem, indexed["item"])
        item.kind = "audio"
        root = session.get(MediaRoot, item.root_id)
        track = session.scalar(select(TextTrack).where(TextTrack.item_id == item.id))
        track.source, track.format, track.relpath = "transcript", "srt", "timed.srt"
        (Path(root.path) / "timed.srt").write_text("1\n00:00:02,000 --> 00:00:04,000\n你好。\n")
        session.commit()
        podcast.ingest_podcast_item(session, item.id)
        assert [(segment.t0_ms, segment.t1_ms) for segment in captured] == [(2000, 4000)]
        assert item.ready
        assert session.scalar(select(Job)).type == "translate_item"


def test_identity_migration_captures_source_and_reserves_historical_ids(tmp_path, monkeypatch):
    from alembic import command
    from alembic.config import Config
    from sqlalchemy.orm import Session
    from app import db
    from app.config import settings
    from app.models import MediaRoot

    monkeypatch.setattr(settings, "data_dir", tmp_path)
    cfg = Config(str(Path(__file__).parents[1] / "src/alembic.ini"))
    cfg.set_main_option("script_location", str(Path(__file__).parents[1] / "src/app/migrations"))
    command.upgrade(cfg, "a2b4c6d8e0f1")
    engine = db.make_engine()
    with Session(engine) as session:
        root = MediaRoot(slug="migration", kind="video", path=str(tmp_path))
        session.add(root)
        session.flush()
        item = MediaItem(root_id=root.id, relpath="a.mp4", title="a", kind="video")
        session.add(item)
        session.flush()
        track = TextTrack(item_id=item.id, lang="zh", source="sidecar")
        session.add(track)
        session.flush()
        session.add(
            Sentence(
                id=42,
                item_id=item.id,
                track_id=track.id,
                ordinal=0,
                zh="學習。",
                en="Study.",
                t0_ms=10,
                t1_ms=1000,
                analysis={"words": []},
            )
        )
        session.add(Event(type="old event", sentence_id=900))
        session.commit()
    db.upgrade_db()
    with Session(engine) as session:
        identity = session.get(SentenceIdentity, 42)
        assert identity.source["zh"] == "學習。"
        assert session.get(Sentence, 42).en == "Study."
        assert session.get(SentenceIdentity, 900) is not None
        reserved = SentenceIdentity(source={})
        session.add(reserved)
        session.flush()
        assert reserved.id > 900
    assert len(list((tmp_path / "backups").glob("*.db"))) == 1


def test_explanation_cache_tracks_local_reading_and_meaning(client, indexed, monkeypatch):
    from app.ai import provider

    calls = []

    def complete(prompt, timeout_s=0):
        calls.append(prompt)
        return {"natural": "Hello.", "literal": "hello", "structure": "A greeting", "words": [{"zh": "你好", "role": "greeting"}], "particles": []}

    monkeypatch.setattr(provider, "available", lambda: True)
    monkeypatch.setattr(provider, "complete_json", complete)
    endpoint = f"/api/sentences/{indexed['sentence']}"
    assert client.post(endpoint + "/explain").status_code == 200
    assert client.post(endpoint + "/explain").status_code == 200
    assert len(calls) == 1
    changed = client.patch(
        endpoint + "/corrections",
        json={
            "expected_revision": 0,
            "words": [{"start": 0, "reading": "ni2 hao3", "meaning": "my scene-specific meaning"}],
        },
    )
    assert changed.status_code == 200
    result = client.post(endpoint + "/explain").json()
    assert len(calls) == 2
    assert "ní" in result["pinyin"]
    assert result["words"][0]["defs"] == ["my scene-specific meaning"]


def test_track_switch_does_not_relink_saved_context_by_text_alone(
    client, indexed, db_session, monkeypatch
):
    install_analysis(monkeypatch)
    saved_id = client.post(
        "/api/saved-items", json={"kind": "sentence", "sentence_id": indexed["sentence"]}
    ).json()["id"]
    with db_session() as session:
        item = session.get(MediaItem, indexed["item"])
        another = TextTrack(item_id=item.id, lang="zh", source="sidecar", relpath="another.srt")
        session.add(another)
        session.flush()
        write_sentences(session, item, another, [Segment(0, 1000, "你好。")], None)
        session.commit()
        context = session.scalar(select(SavedContext).where(SavedContext.saved_item_id == saved_id))
        assert context.sentence_id is None
        assert context.snapshot["zh"] == "你好。"


@pytest.mark.parametrize("during_request", [False, True])
def test_automatic_translation_respects_local_edits(
    client, indexed, db_session, monkeypatch, during_request
):
    from app.ai import provider
    from app.ai.tasks import translate_item

    monkeypatch.setattr(provider, "available", lambda: True)
    endpoint = f"/api/sentences/{indexed['sentence']}/corrections"
    if not during_request:
        assert client.patch(endpoint, json={"expected_revision": 0, "en": None}).status_code == 200

    def complete(prompt):
        assert during_request, "Explicitly cleared user translation must not trigger AI"
        assert (
            client.patch(
                endpoint, json={"expected_revision": 0, "en": "Local meaning wins"}
            ).status_code
            == 200
        )
        assert (
            client.post(f"/api/items/{indexed['item']}/tracks", json={"zh_track_id": 1}).status_code
            == 200
        )
        return ["AI must not overwrite my edit"]

    monkeypatch.setattr(provider, "complete_json", complete)
    with db_session() as session:
        result = translate_item(session, indexed["item"])
        assert result["translated"] == 0
        sentence = session.get(Sentence, indexed["sentence"])
        assert sentence.en == ("Local meaning wins" if during_request else None)
        assert sentence.en_source == "user"
        if during_request:
            assert session.get(MediaItem, indexed["item"]).meta["track_choices"]["zh"] == 1


def test_empty_embedded_cache_is_extracted_again(indexed, db_session, tmp_path, monkeypatch):
    from app.config import settings
    from app.ingest import embedded

    monkeypatch.setattr(type(settings), "subs_dir", property(lambda _: tmp_path / "subs"))
    calls = []

    def extract(video, index, output):
        calls.append(index)
        output.write_text("1\n00:00:00,000 --> 00:00:01,000\n你好。\n")
        return True

    monkeypatch.setattr(embedded, "extract_stream", extract)
    with db_session() as session:
        item = session.get(MediaItem, indexed["item"])
        item.meta = {"embedded_subs": [{"index": 1, "codec": "subrip", "lang": "zh"}]}
        output = embedded.sub_path(item.id, 1, item.fingerprint)
        output.parent.mkdir(parents=True)
        output.write_bytes(b"")
        tracks = embedded.ensure_embedded_tracks(session, item, tmp_path / "source.mkv")
        assert calls == [1] and tracks[0].meta["available"]
        assert output.stat().st_size > 0


def test_export_does_not_synthesize_a_locally_corrected_word_reading(
    client, indexed, db_session, monkeypatch
):
    from app.anki import export

    response = client.patch(
        f"/api/sentences/{indexed['sentence']}/corrections",
        json={"expected_revision": 0, "words": [{"start": 0, "reading": "ni2 hao3"}]},
    )
    assert response.status_code == 200
    saved_id = client.post(
        "/api/saved-items",
        json={"kind": "word", "lexeme_id": indexed["lexeme"], "sentence_id": indexed["sentence"]},
    ).json()["id"]
    synthesized = []

    def ac(action, **kwargs):
        if action == "modelFieldNames":
            return ["ID", "Simplified", "Audio"]
        if action == "addNote":
            return 333

    monkeypatch.setattr(export, "ac", ac)
    monkeypatch.setattr(export, "_media_source", lambda *args: None)
    monkeypatch.setattr(export, "_tts", lambda word: synthesized.append(word))
    with db_session() as session:
        result = export.export_items(
            session, [{"saved_item_id": saved_id, "fields": {"ID": "hello", "Simplified": "你好"}}]
        )
        assert result["added"] == 1
    assert synthesized == []
