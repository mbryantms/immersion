"""Podcast scan: first-integer pairing, ambiguity skip, mtime guard,
transcript-change re-ingest, and .srt transcript stripping."""

import os
import time
from pathlib import Path

import pytest
from sqlalchemy import select
from sqlalchemy.orm import sessionmaker

from app.db import make_engine
from app.ingest import podcast
from app.ingest.podcast import first_int, read_transcript, scan_podcast_root
from app.models import Base, MediaItem, MediaRoot, Series, TextTrack


def test_first_int():
    assert first_int("episode-6-transcript.txt") == 6
    assert first_int("第06集：新疆.mp3") == 6
    assert first_int("no-number.wav") is None  # note: ".mp3" itself contains a 3


def test_read_transcript_strips_bom_and_srt(tmp_path: Path):
    txt = tmp_path / "episode-1-transcript.txt"
    txt.write_text("﻿大家好。欢迎回来。", encoding="utf-8")
    assert read_transcript(txt) == "大家好。欢迎回来。"  # sniff_read strips the BOM

    srt = tmp_path / "episode-2-transcript.srt"
    srt.write_text("1\n00:00:01,000 --> 00:00:03,000\n大家好。\n\n2\n00:00:03,000 --> 00:00:05,000\n欢迎回来。\n")
    assert read_transcript(srt) == "大家好。欢迎回来。"


@pytest.fixture()
def db(tmp_path: Path):
    engine = make_engine(tmp_path / "test.db")
    Base.metadata.create_all(engine)
    return sessionmaker(engine, expire_on_commit=False)


@pytest.fixture()
def podcast_root(tmp_path: Path):
    show = tmp_path / "podcasts" / "TeaTime Chinese 茶歇中文"
    show.mkdir(parents=True)
    (show / "episode-6-transcript.txt").write_text("﻿大家好。")
    (show / "第06集：新疆.mp3").write_bytes(b"fake-audio-6")
    (show / "cover.jpg").write_bytes(b"fake-jpeg")
    # ambiguous: two audios share the transcript's episode number
    (show / "episode-7-transcript.txt").write_text("你好。")
    (show / "ep-7a-7.mp3").write_bytes(b"a")
    (show / "7-second-version.mp3").write_bytes(b"b")
    # age the files past the mtime guard
    old = time.time() - 3600
    for p in show.iterdir():
        os.utime(p, (old, old))
    return tmp_path / "podcasts"


@pytest.fixture(autouse=True)
def no_ffprobe(monkeypatch):
    monkeypatch.setattr(
        podcast, "probe_summary",
        lambda p: {"duration_ms": 60_000, "vcodec": None, "acodec": "mp3",
                   "width": None, "height": None, "embedded_subs": []},
    )
    monkeypatch.setattr(podcast, "fingerprint", lambda p: f"fp:{p.stat().st_size}")


def test_scan_pairs_and_skips_ambiguous(db, podcast_root: Path):
    with db() as s:
        root = MediaRoot(slug="podcasts", kind="podcast", path=str(podcast_root))
        s.add(root)
        s.commit()
        result = scan_podcast_root(s, root)
        assert result["stats"]["new"] == 1
        assert result["stats"]["skipped"] == 1  # episode 7: two matching audios

        item = s.scalars(select(MediaItem)).one()
        assert item.kind == "audio"
        assert item.ordinal == 6
        assert (item.meta or {}).get("cover") is not None
        series = s.get(Series, item.series_id)
        assert series.title == "TeaTime Chinese 茶歇中文"
        track = s.scalars(select(TextTrack).where(TextTrack.item_id == item.id)).one()
        assert (track.lang, track.source) == ("zh", "transcript")
        assert result["ingest_item_ids"] == [item.id]


def test_rescan_unchanged_then_transcript_edit(db, podcast_root: Path):
    with db() as s:
        root = MediaRoot(slug="podcasts", kind="podcast", path=str(podcast_root))
        s.add(root)
        s.commit()
        scan_podcast_root(s, root)

        result = scan_podcast_root(s, root)
        assert result["stats"]["unchanged"] == 1
        assert result["ingest_item_ids"] == []

        t = podcast_root / "TeaTime Chinese 茶歇中文" / "episode-6-transcript.txt"
        t.write_text("﻿大家好。今天我们聊聊。")
        old = time.time() - 3600
        os.utime(t, (old, old))
        result = scan_podcast_root(s, root)
        assert result["stats"]["changed"] == 1
        assert len(result["ingest_item_ids"]) == 1


def test_mtime_guard_skips_fresh_transcript(db, podcast_root: Path):
    fresh = podcast_root / "TeaTime Chinese 茶歇中文" / "episode-8-transcript.txt"
    fresh.write_text("新的。")  # mtime = now → still being written
    audio = podcast_root / "TeaTime Chinese 茶歇中文" / "episode-8.mp3"
    audio.write_bytes(b"x")
    with db() as s:
        root = MediaRoot(slug="podcasts", kind="podcast", path=str(podcast_root))
        s.add(root)
        s.commit()
        result = scan_podcast_root(s, root)
        relpaths = set(s.scalars(select(MediaItem.relpath)))
        assert not any("episode-8" in r for r in relpaths)
        assert result["stats"]["skipped"] >= 2  # ambiguous ep7 + fresh ep8
