# ruff: noqa: F811
"""Mandarin representation regressions; no NLP downloads or remote services."""
from pathlib import Path
import sqlite3

import pytest
from sqlalchemy import select, text

from app.lingua.cedict import Cedict
from app.lingua import pipeline
from app.lingua.diff import score_attempt
from app.lingua.script_policy import script_variants
from app.ingest.analysis import link_words, token_occurrences
from app.models import SavedItem, Sentence, KnowledgeState
from app.api.review import _mark_known_on_graduation
from app.anki.export import _fields
from app.db import verified_backup
from test_api import client, db_session, seeded  # noqa: F401


@pytest.fixture()
def dictionary(tmp_path):
    path = tmp_path / "cedict.txt"
    path.write_text("學習 学习 [xue2 xi2] /to study/\n銀行 银行 [yin2 hang2] /bank/\n音樂 音乐 [yin1 yue4] /music/\n還 还 [hai2] /still/\n還 还 [huan2] /return/\n長 长 [zhang3] /grow/\n長 长 [chang2] /long/\n地 地 [di4] /earth/\n地 地 [de5] /adverb particle/\n重 重 [zhong4] /heavy/\n重 重 [chong2] /again/\n行 行 [xing2] /walk/\n行 行 [hang2] /row/\n", encoding="utf-8")
    return Cedict(path)


def analyze(monkeypatch, dictionary, sentence, tokens):
    from app.lingua.convert import t2s
    monkeypatch.setattr(pipeline, "tokenize", lambda _: [[t2s(token) for token in tokens]])
    monkeypatch.setattr(pipeline, "ner_entities", lambda _: [[]])
    return pipeline.analyze_sentences([sentence], dictionary)[0]


def test_traditional_reconciliation_and_source_offsets(monkeypatch, dictionary):
    source = "學習 銀行，音樂。學習𠀀。"
    words = analyze(monkeypatch, dictionary, source, ["學習", "銀行", "，", "音樂", "。", "學習", "𠀀", "。"])
    assert "".join(w["t"] for w in words) == source
    zh = [w for w in words if w["type"] == "zh"]
    assert [w["canonical"] for w in zh] == ["学习", "银行", "音乐", "学习", "𠀀"]
    assert zh[1]["reading"] == "yin2 hang2"
    assert zh[2]["reading"] == "yin1 yue4"
    assert zh[3]["start"] == 9
    ids = {w["t"]: i for i, w in enumerate(zh, 1)}
    link_words(source, words, ids)
    sentence = Sentence(id=1, zh=source, analysis={"words": words})
    occurrences = token_occurrences(1, [sentence])
    for occurrence in occurrences:
        assert source[occurrence.start_offset:occurrence.end_offset] == occurrence.surface


@pytest.mark.parametrize("source,tokens,expected", [
    ("他还没有还钱。", ["他", "还", "没有", "还", "钱", "。"], ["hai2", "huan2"]),
    ("长大去长江。", ["长大", "去", "长江", "。"], ["zhang3 da4", "chang2 jiang1"]),
    ("银行走路行走。", ["银行", "走路", "行走", "。"], ["yin2 hang2", "xing2 zou3"]),
    ("重新很重。", ["重新", "很", "重", "。"], ["chong2 xin1", "zhong4"]),
    ("地球的地方。", ["地球", "的", "地方", "。"], ["di4 qiu2", "di4 fang1"]),
])
def test_phrase_readings(monkeypatch, dictionary, source, tokens, expected):
    # OOV reconciliation may split a phrase; concatenated occurrence readings
    # must still reflect sentence-level disambiguation.
    words = analyze(monkeypatch, dictionary, source, tokens)
    readings = " ".join(w.get("reading", "") for w in words)
    for reading in expected:
        assert reading in readings
    assert all(w.get("reading_source") == "pypinyin-context" for w in words if w["type"] == "zh")


def test_code_switch_and_supplementary_characters(monkeypatch, dictionary):
    source = "我是 Nathan 2026。𠀀"
    words = analyze(monkeypatch, dictionary, source, ["我", "是", "Nathan", "2026", "。", "𠀀"])
    assert "".join(w["t"] for w in words) == source
    assert pipeline.split_sentences(source) == ["我是 Nathan 2026。", "𠀀"]
    assert words[-1]["end"] == len(source)


def test_script_policy_is_explicit_and_conservative():
    assert score_attempt("学习", "學習").score < 1
    assert score_attempt("学习", "學習", "equivalent").score == 1
    assert score_attempt("學習", "学习", "equivalent").score == 1
    for source, typed in [("头发", "頭髮"), ("后", "後"), ("干", "幹"), ("里面", "裏面")]:
        assert score_attempt(source, typed, "equivalent").score < 1
    assert script_variants("学习") == {"學": "学", "習": "习"}


def test_selected_senses_are_distinct_and_preserved(client, seeded, db_session):
    base = {"kind": "word", "lexeme_id": seeded["lexeme"], "sentence_id": seeded["sentence"], "surface": "你好"}
    first = client.post("/api/saved-items", json={**base, "selected_reading": "ni3 hao3", "selected_meaning": "hello"}).json()
    retry = client.post("/api/saved-items", json={**base, "selected_reading": "ni3 hao3", "selected_meaning": "hello"}).json()
    second = client.post("/api/saved-items", json={**base, "selected_reading": "ni3 hao3", "selected_meaning": "how are you"}).json()
    assert first["id"] == retry["id"] != second["id"]
    with db_session() as session:
        saved = session.get(SavedItem, first["id"])
        _mark_known_on_graduation(session, saved)
        assert session.get(KnowledgeState, seeded["lexeme"]).state == "learning"
        fields, _ = _fields(session, saved)
        assert fields["Meaning"] == "hello"
        assert fields["Pinyin"] == "nǐ hǎo"
        assert "-s" in fields["ID"]
        assert saved.contexts[0].snapshot["analysis"]["words"][0]["t"] == "你好"
    bad = client.post("/api/saved-items", json={**base, "occurrence_start": 99})
    assert bad.status_code == 400


def test_lookup_source_codepoints_and_traditional(client, seeded, db_session):
    with db_session() as session:
        sentence = session.get(Sentence, seeded["sentence"])
        sentence.zh = "𠀀你好你好。"
        session.commit()
    result = client.post("/api/lookup", json={"sentence_id": seeded["sentence"], "start": 3, "end": 5})
    assert result.json()["span"] == "你好"
    assert result.json()["candidates"][0]["lexeme_id"] == seeded["lexeme"]
    assert client.post("/api/lookup", json={"sentence_id": seeded["sentence"], "start": -1, "end": 5}).status_code == 400


def test_online_backup_restores_wal(tmp_path):
    path = tmp_path / "source.db"
    with sqlite3.connect(path) as connection:
        connection.execute("PRAGMA journal_mode=WAL")
        connection.execute("CREATE TABLE personal_data(value TEXT)")
        connection.execute("INSERT INTO personal_data VALUES ('saved learning history')")
        connection.commit()
        backup = verified_backup(path, tmp_path / "backups" / "backup.db")
        with sqlite3.connect(backup) as restored:
            assert restored.execute("SELECT value FROM personal_data").fetchone()[0] == "saved learning history"


def test_mixed_script_source_is_not_swapped():
    assert score_attempt("学學", "学學", "equivalent").score == 1


def test_migration_preserves_legacy_rows_and_verified_restore(tmp_path, monkeypatch):
    from alembic import command
    from alembic.config import Config
    from app import db
    from app.config import settings
    monkeypatch.setattr(settings, "data_dir", tmp_path)
    cfg = Config(str(Path(__file__).parents[1] / "src/alembic.ini"))
    cfg.set_main_option("script_location", str(Path(__file__).parents[1] / "src/app/migrations"))
    command.upgrade(cfg, "e8c1b6f4a9d3")
    with sqlite3.connect(settings.db_path) as connection:
        connection.execute("INSERT INTO saved_item(id,kind,surface,archived,created_at) VALUES (42,'sentence','學習',0,'2026-10-18')")
        connection.commit()
    db.upgrade_db()
    with sqlite3.connect(settings.db_path) as connection:
        assert connection.execute("SELECT id,surface,selected_meaning FROM saved_item").fetchone() == (42, "學習", None)
    backups = list((tmp_path / "backups").glob("*.db"))
    assert len(backups) == 1
    with sqlite3.connect(backups[0]) as restored:
        assert restored.execute("SELECT id,surface FROM saved_item").fetchone() == (42, "學習")
    db.upgrade_db()
    assert len(list((tmp_path / "backups").glob("*.db"))) == 1


def test_reanalysis_keeps_saved_sense_and_sentence_identity(monkeypatch, dictionary, db_session, seeded):
    from app.ingest import analysis
    from app.models import TokenOccurrence
    monkeypatch.setattr(analysis, "load_cedict", lambda: dictionary)
    monkeypatch.setattr(analysis, "hsk_levels", lambda: {})
    with db_session() as session:
        sentence = session.get(Sentence, seeded["sentence"])
        sentence.zh = "學習 學習。"
        session.commit()
        words = analyze(monkeypatch, dictionary, sentence.zh, ["學習", "學習", "。"])
        monkeypatch.setattr(analysis, "analyze_sentences", lambda *args, **kwargs: [words])
        saved = SavedItem(kind="word", lexeme_id=seeded["lexeme"], surface="你好", selected_reading="ni3 hao3", selected_meaning="hello")
        session.add(saved)
        session.commit()
        session.execute(text("CREATE VIRTUAL TABLE sentence_fts USING fts5(zh_words,zh_chars,trad_words,pinyin,en)"))
        analysis.reanalyze_item(session, seeded["item"])
        assert session.get(Sentence, seeded["sentence"]).zh == "學習 學習。"
        assert session.get(SavedItem, saved.id).selected_meaning == "hello"
        rows = session.scalars(select(TokenOccurrence).order_by(TokenOccurrence.idx)).all()
        assert [r.start_offset for r in rows] == [0, 3]
        assert rows[0].lexeme_id == rows[1].lexeme_id
        assert [r.canonical for r in rows] == ["学习", "学习"]


def test_selected_occurrence_reading_survives_reanalysis_and_export(client, seeded, db_session, monkeypatch):
    from app.ingest import analysis
    from app.models import TokenOccurrence
    with db_session() as session:
        sentence = session.get(Sentence, seeded["sentence"])
        words = [{"t": "你好", "type": "zh", "lex": seeded["lexeme"], "start": start, "end": start + 2,
                  "py": ["nǐ", "hǎo"], "tones": [3, 3], "reading": "ni3 hao3"} for start in (0, 2)]
        sentence.zh = "你好你好"
        sentence.analysis = {"words": words}
        session.add(TokenOccurrence(sentence_id=sentence.id, idx=1, item_id=seeded["item"], surface="你好", lexeme_id=seeded["lexeme"], start_offset=2, end_offset=4))
        session.commit()
    response = client.post("/api/saved-items", json={"kind": "word", "lexeme_id": seeded["lexeme"], "surface": "你好", "sentence_id": seeded["sentence"], "occurrence_start": 2, "selected_reading": "ni2 hao3", "selected_meaning": "chosen meaning"})
    assert response.status_code == 200
    saved_id = response.json()["id"]
    monkeypatch.setattr(analysis, "analyze_sentences", lambda *args, **kwargs: [[dict(w) for w in words]])
    monkeypatch.setattr(analysis, "get_or_create_lexemes", lambda *args: {"你好": seeded["lexeme"]})
    with db_session() as session:
        session.execute(text("CREATE VIRTUAL TABLE sentence_fts USING fts5(zh_words,zh_chars,trad_words,pinyin,en)"))
        analysis.reanalyze_item(session, seeded["item"])
        sentence = session.get(Sentence, seeded["sentence"])
        assert [w["reading"] for w in sentence.analysis["words"]] == ["ni3 hao3", "ni2 hao3"]
        fields, _ = _fields(session, session.get(SavedItem, saved_id))
        assert fields["Pinyin"] == "ní hǎo"
        assert fields["SentencePinyin"] == "nǐ hǎo ní hǎo"
    queue = client.get("/api/review/queue").json()["items"]
    assert queue[0]["answer"]["pinyin"] == "ni2 hao3"
    assert queue[0]["answer"]["senses"][0]["defs"] == ["chosen meaning"]


def test_repeated_saved_selection_keeps_both_occurrence_corrections(client, seeded, db_session):
    from app.ingest.analysis import selected_readings, restore_selected_readings
    with db_session() as session:
        sentence = session.get(Sentence, seeded["sentence"])
        words = [{"t": "你好", "type": "zh", "lex": seeded["lexeme"], "start": start, "end": start + 2} for start in (0, 2)]
        sentence.zh = "你好你好"
        sentence.analysis = {"words": words}
        session.commit()
    base = {"kind": "word", "lexeme_id": seeded["lexeme"], "surface": "你好", "sentence_id": seeded["sentence"], "selected_reading": "ni2 hao3", "selected_meaning": "hello"}
    first = client.post("/api/saved-items", json={**base, "occurrence_start": 0}).json()
    second = client.post("/api/saved-items", json={**base, "occurrence_start": 2}).json()
    assert first["id"] == second["id"]
    with db_session() as session:
        restore_selected_readings(selected_readings(session, seeded["item"]), "你好你好", words, 0)
        assert [w["reading"] for w in words] == ["ni2 hao3", "ni2 hao3"]
