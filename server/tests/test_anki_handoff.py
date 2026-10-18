"""Persistent handoff uses a local Anki double; no personal collection is contacted."""

# ruff: noqa: F811
import copy
import json
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from uuid import uuid4

import pytest
from sqlalchemy import select

from app.anki import export, handoff, profile
from app.anki.connect import AnkiError, AnkiUnavailable
from app.models import (
    AnkiLink,
    Event,
    ExportAttempt,
    Job,
    KnowledgeState,
    LearningEvidence,
    ReviewState,
    SavedItem,
    Sentence,
)
from app.worker import run_one
from test_api import client, db_session, seeded  # noqa: F401

PROFILE = {
    "deck": "Mandarin",
    "model": "Local Mandarin",
    "fields": {
        "ID": "Key",
        "Simplified": "Hanzi",
        "Pinyin": "Reading",
        "Meaning": "Gloss",
        "Sentence": "Context",
        "SentenceMeaning": "ContextMeaning",
        "SentenceAudio": "SourceAudio",
        "Image": "Pic",
    },
    "templates_reviewed": True,
    "word_tts": False,
}


class FakeAnki:
    def __init__(self):
        self.notes = {}
        self.calls = []
        self.mode = "ok"
        self.add_calls = 0
        self.fields = [
            "Key",
            "Hanzi",
            "Reading",
            "Gloss",
            "Context",
            "ContextMeaning",
            "SourceAudio",
            "Pic",
        ]

    def __call__(self, action, **params):
        self.calls.append((action, copy.deepcopy(params)))
        if self.mode == "offline":
            raise AnkiUnavailable("Anki is offline")
        if action == "version":
            return 6
        if action == "modelNames":
            return ["Local Mandarin", "Basic"]
        if action == "deckNames":
            return ["Mandarin"]
        if action == "modelFieldNames":
            return self.fields if params["modelName"] == "Local Mandarin" else ["Front", "Back"]
        if action == "findNotes":
            query = params["query"]
            if query.startswith("tag:"):
                return [
                    note_id for note_id, note in self.notes.items() if query[4:] in note["tags"]
                ]
            field, value = json.loads(query).split(":", 1)
            return [
                note_id
                for note_id, note in self.notes.items()
                if note["fields"].get(field) == value
            ]
        if action == "notesInfo":
            return [
                {
                    "noteId": note_id,
                    "fields": {
                        name: {"value": value}
                        for name, value in self.notes[note_id]["fields"].items()
                    },
                }
                for note_id in params["notes"]
            ]
        if action == "storeMediaFile":
            return params["filename"]
        if action == "addNote":
            self.add_calls += 1
            if self.mode == "reject":
                raise AnkiError("Anki rejected the note")
            note_id = 1000 + len(self.notes)
            self.notes[note_id] = copy.deepcopy(params["note"])
            if self.mode == "lost":
                raise AnkiUnavailable("Reply lost after add")
            return note_id
        raise AssertionError(action)


@pytest.fixture()
def setup(client, seeded, db_session, monkeypatch):
    fake = FakeAnki()
    for module in (handoff, profile, export):
        monkeypatch.setattr(module, "ac", fake)
    saved = client.post(
        "/api/saved-items",
        json={
            "kind": "word",
            "lexeme_id": seeded["lexeme"],
            "sentence_id": seeded["sentence"],
            "surface": "你好",
            "selected_reading": "ni3 hao3",
            "selected_meaning": "hello",
        },
    ).json()["id"]
    response = client.put("/api/anki/export-profile", json=PROFILE)
    assert response.status_code == 200, response.text
    return fake, saved


def payload(client, saved, **changes):
    preview = client.post("/api/anki/export-preview", json={"saved_item_ids": [saved]})
    assert preview.status_code == 200, preview.text
    value = preview.json()
    row = value["items"][0]
    entry = {
        "saved_item_id": saved,
        "source_hash": row["source_hash"],
        "meaning": "selected edited meaning",
        "include_media": False,
        **changes,
    }
    return {"request_uuid": str(uuid4()), "profile_hash": value["profile_hash"], "entries": [entry]}


def process(db_session, job_id):
    from app.jobs import handlers  # noqa: F401

    with db_session() as session:
        job = session.get(Job, job_id)
        job.status = "running"
        session.commit()
        run_one(session, job)
        assert job.status == "done", job.error
        return session.scalar(select(ExportAttempt).where(ExportAttempt.job_id == job_id)).id


def test_config_preflight_custom_mapping_and_missing_fields(client, setup):
    fake, _ = setup
    check = client.post("/api/anki/preflight", json=PROFILE).json()
    assert check["ok"] and check["model_fields"] == fake.fields
    fake.fields.remove("Reading")
    response = client.put("/api/anki/export-profile", json=PROFILE)
    assert response.status_code == 422 and "Reading" in response.text
    assert client.get("/api/anki/export-profile").json()["profile"] == PROFILE
    fake.mode = "offline"
    assert client.post("/api/anki/preflight", json=PROFILE).status_code == 503


@pytest.mark.parametrize(
    "patch",
    [
        {"templates_reviewed": False},
        {"deck": "Missing"},
        {"model": "Missing"},
        {"fields": {"Simplified": "Hanzi", "Meaning": "Gloss"}},
    ],
)
def test_preflight_blocks_unreviewed_missing_or_blank_first_field(client, setup, patch):
    response = client.post("/api/anki/preflight", json={**PROFILE, **patch})
    assert response.status_code == 200 and not response.json()["ok"]


@pytest.mark.parametrize(
    "mapping",
    [
        {"Simplified": "Hanzi", "Meaning": "Hanzi"},
        {"Simplified": "Hanzi", "Meaning": "Gloss", "Injected": "Reading"},
        {"Simplified": "Hanzi"},
    ],
)
def test_mapping_rejects_duplicate_unknown_and_missing_sources(client, setup, mapping):
    assert (
        client.put("/api/anki/export-profile", json={**PROFILE, "fields": mapping}).status_code
        == 422
    )


def test_submission_replay_freezes_fields_and_full_status_survives_progress_truncation(
    client, setup, db_session
):
    fake, saved = setup
    body = payload(client, saved)
    first = client.post("/api/anki/export", json=body)
    assert first.status_code == 200, first.text
    job_id = first.json()["job_id"]
    assert client.post("/api/anki/export", json=body).json()["job_id"] == job_id
    conflict = copy.deepcopy(body)
    conflict["entries"][0]["meaning"] = "different"
    assert client.post("/api/anki/export", json=conflict).status_code == 409
    attempt_id = process(db_session, job_id)
    note = next(iter(fake.notes.values()))
    assert (
        note["fields"]["Hanzi"] == "你好" and note["fields"]["Gloss"] == "selected edited meaning"
    )
    assert note["fields"]["Reading"] == "nǐ hǎo"
    assert note["modelName"] == PROFILE["model"] and note["deckName"] == PROFILE["deck"]
    assert len(note["tags"]) == 2
    with db_session() as session:
        assert (
            session.get(ExportAttempt, attempt_id).snapshot["fields"]["Meaning"]
            == "selected edited meaning"
        )
        session.get(Job, job_id).progress = "truncated invalid JSON"
        session.commit()
        assert session.query(AnkiLink).count() == 1
        assert session.query(LearningEvidence).count() == 0
        assert session.get(KnowledgeState, 1).state != "known"
    result = client.get(f"/api/anki/exports/{job_id}").json()
    assert result["items"][0]["note_id"] == 1000 and result["items"][0]["status"] == "added"
    assert (
        client.get("/api/anki/exports").json()["batches"][0]["items"][0]["fields"]["Meaning"]
        == "selected edited meaning"
    )
    process(db_session, job_id)
    assert fake.add_calls == 1


def test_lost_add_reply_reconciles_without_second_add(client, setup, db_session):
    fake, saved = setup
    job_id = client.post("/api/anki/export", json=payload(client, saved)).json()["job_id"]
    fake.mode = "lost"
    attempt_id = process(db_session, job_id)
    with db_session() as session:
        assert session.get(ExportAttempt, attempt_id).status == "uncertain"
        assert session.query(AnkiLink).count() == 0
    assert client.post("/api/anki/export", json=payload(client, saved)).status_code == 409
    assert (
        client.post(
            f"/api/anki/export-attempts/{attempt_id}/retry", json={"request_uuid": str(uuid4())}
        ).status_code
        == 409
    )
    fake.mode = "ok"
    response = client.post(f"/api/anki/export-attempts/{attempt_id}/reconcile")
    assert response.status_code == 200 and response.json()["status"] == "added"
    assert fake.add_calls == 1


def test_worker_restart_after_uncertain_does_not_readd_when_tag_absent(client, setup, db_session):
    fake, saved = setup
    job_id = client.post("/api/anki/export", json=payload(client, saved)).json()["job_id"]
    with db_session() as session:
        row = session.scalar(select(ExportAttempt))
        row.status = "uncertain"
        session.commit()
    attempt_id = process(db_session, job_id)
    assert not fake.add_calls
    body = {"request_uuid": str(uuid4()), "confirm_no_note": True}
    retry = client.post(f"/api/anki/export-attempts/{attempt_id}/retry", json=body)
    assert retry.status_code == 200
    assert (
        client.post(f"/api/anki/export-attempts/{attempt_id}/retry", json=body).json()
        == retry.json()
    )
    process(db_session, retry.json()["job_id"])
    assert fake.add_calls == 1
    assert (
        client.post(
            f"/api/anki/export-attempts/{attempt_id}/retry",
            json={**body, "request_uuid": str(uuid4())},
        ).status_code
        == 409
    )


def test_source_and_profile_changes_require_new_preview(client, setup, db_session, seeded):
    _, saved = setup
    body = payload(client, saved)
    with db_session() as session:
        session.get(Sentence, seeded["sentence"]).en = "Changed translation"
        session.commit()
    assert client.post("/api/anki/export", json=body).status_code == 409
    fresh = payload(client, saved)
    assert (
        client.put("/api/anki/export-profile", json={**PROFILE, "word_tts": True}).status_code
        == 200
    )
    assert client.post("/api/anki/export", json=fresh).status_code == 409


def test_changed_source_after_submission_preserves_snapshot_without_add(
    client, setup, db_session, seeded
):
    fake, saved = setup
    job_id = client.post("/api/anki/export", json=payload(client, saved)).json()["job_id"]
    with db_session() as session:
        session.get(Sentence, seeded["sentence"]).en = "Changed after acceptance"
        session.commit()
    attempt_id = process(db_session, job_id)
    with db_session() as session:
        row = session.get(ExportAttempt, attempt_id)
        assert row.status == "error" and "changed" in row.error
        assert row.snapshot["fields"]["SentenceMeaning"] != "Changed after acceptance"
    assert fake.add_calls == 0


def test_duplicate_permission_is_explicit_and_never_changes_chinese_front(
    client, setup, db_session
):
    fake, saved = setup
    fake.notes[80] = {"fields": {"Hanzi": "你好", "Gloss": "existing"}, "tags": []}
    job = client.post("/api/anki/export", json=payload(client, saved)).json()["job_id"]
    process(db_session, job)
    assert fake.add_calls == 0
    job = client.post("/api/anki/export", json=payload(client, saved, allow_duplicate=True)).json()[
        "job_id"
    ]
    process(db_session, job)
    assert fake.add_calls == 1
    assert fake.notes[1001]["fields"]["Hanzi"] == "你好"


def test_inbox_defer_restore_sql_paging_suspension_and_link_exclusion(client, setup, db_session):
    _, saved = setup
    with db_session() as session:
        session.add(ReviewState(saved_item_id=saved, graduated=True))
        for index in range(5):
            item = SavedItem(kind="sentence", surface=f"句子{index}")
            session.add(item)
            session.flush()
            session.add(ReviewState(saved_item_id=item.id, graduated=True))
        session.commit()
    first = client.get("/api/anki/inbox?limit=2").json()
    second = client.get(f"/api/anki/inbox?limit=2&before_id={first['next_cursor']}").json()
    assert first["counts"]["ready"] == 6
    assert {item["id"] for item in first["items"]}.isdisjoint(
        {item["id"] for item in second["items"]}
    )
    assert client.put(f"/api/anki/inbox/{saved}", json={"deferred": True}).status_code == 200
    assert client.get("/api/anki/inbox").json()["counts"] == {"ready": 5, "deferred": 1}
    assert client.get("/api/stats/dashboard").json()["graduated_waiting"] == 5
    assert client.get("/api/anki/inbox?view=deferred").json()["items"][0]["id"] == saved
    client.put(f"/api/anki/inbox/{saved}", json={"deferred": False})
    client.patch(f"/api/saved-items/{saved}", json={"archived": True})
    assert client.get("/api/anki/inbox").json()["counts"]["ready"] == 5
    client.patch(f"/api/saved-items/{saved}", json={"archived": False})
    job = client.post("/api/anki/export", json=payload(client, saved)).json()["job_id"]
    process(db_session, job)
    assert client.get("/api/anki/inbox").json()["counts"]["ready"] == 5
    with db_session() as session:
        assert session.get(ReviewState, saved).graduated


def test_removed_saved_id_cannot_reassign_old_export_tag(client, setup, db_session):
    fake, saved = setup
    job_id = client.post("/api/anki/export", json=payload(client, saved)).json()["job_id"]
    client.delete(f"/api/saved-items/{saved}")
    with db_session() as session:
        original = session.scalar(select(ExportAttempt))
        tag = original.export_key
        assert original.saved_item_id is None and original.original_saved_item_id == saved
        fresh = SavedItem(kind="sentence", surface="new")
        session.add(fresh)
        session.commit()
        assert handoff.latest(session, fresh.id) is None
        assert session.scalar(select(ExportAttempt)).export_key == tag
    process(db_session, job_id)
    assert fake.add_calls == 0


def test_submission_uuid_replay_survives_anki_offline_and_blocks_double_queue(
    client, setup, db_session
):
    fake, saved = setup
    body = payload(client, saved)
    one = client.post("/api/anki/export", json=body)
    fake.mode = "offline"
    assert client.post("/api/anki/export", json=body).json()["job_id"] == one.json()["job_id"]
    with db_session() as session:
        assert session.query(Job).count() == 1


def test_migration_preserves_review_cards_events_and_verified_backup(tmp_path, monkeypatch):
    from alembic import command
    from alembic.config import Config
    from sqlalchemy import text
    from sqlalchemy.orm import Session
    from app import db
    from app.config import settings

    monkeypatch.setattr(settings, "data_dir", tmp_path)
    cfg = Config(str(Path(__file__).parents[1] / "src/alembic.ini"))
    cfg.set_main_option("script_location", str(Path(__file__).parents[1] / "src/app/migrations"))
    command.upgrade(cfg, "e5f7a9b1c3d5")
    engine = db.make_engine()
    with Session(engine) as session:
        session.execute(
            text(
                "INSERT INTO saved_item(id,kind,surface,archived,created_at) VALUES(1,'sentence','original',0,CURRENT_TIMESTAMP)"
            )
        )
        session.execute(
            text(
                "INSERT INTO review_state(saved_item_id,rung,due_at,passes,fails,streak,graduated,updated_at) VALUES(1,2,CURRENT_TIMESTAMP,3,0,3,1,CURRENT_TIMESTAMP)"
            )
        )
        session.add(Event(type="preserve", data={"original": True}))
        session.commit()
    db.upgrade_db()
    with Session(engine) as session:
        assert (
            session.get(SavedItem, 1).surface == "original"
            and not session.get(SavedItem, 1).export_deferred
        )
        assert session.get(ReviewState, 1).graduated and session.get(ReviewState, 1).passes == 3
        assert session.query(Event).one().data == {"original": True}
        assert session.query(ExportAttempt).count() == 0
    assert list((tmp_path / "backups").glob("*.db"))


@pytest.mark.parametrize("same_uuid", [True, False])
def test_concurrent_submissions_never_queue_the_same_card_twice(
    client, setup, db_session, same_uuid
):
    _, saved = setup
    first = payload(client, saved)
    second = copy.deepcopy(first)
    if not same_uuid:
        second["request_uuid"] = str(uuid4())
    with ThreadPoolExecutor(max_workers=2) as pool:
        replies = list(
            pool.map(lambda body: client.post("/api/anki/export", json=body), [first, second])
        )
    assert sorted(reply.status_code for reply in replies) == (
        [200, 200] if same_uuid else [200, 409]
    )
    with db_session() as session:
        assert session.query(Job).count() == 1
        assert session.query(ExportAttempt).count() == 1


def test_selected_reading_cannot_be_silently_dropped_by_mapping(client, setup):
    _, saved = setup
    mapping = {key: value for key, value in PROFILE["fields"].items() if key != "Pinyin"}
    assert (
        client.put("/api/anki/export-profile", json={**PROFILE, "fields": mapping}).status_code
        == 200
    )
    check = client.post("/api/anki/export-preview", json={"saved_item_ids": [saved]}).json()
    assert "selected reading" in check["items"][0]["errors"][0]
    assert client.post("/api/anki/export", json=payload(client, saved)).status_code == 409


def test_source_edit_during_media_preparation_is_detected(
    client, setup, db_session, seeded, monkeypatch
):
    fake, saved = setup
    body = payload(client, saved, include_media=True)
    job = client.post("/api/anki/export", json=body).json()["job_id"]

    def change(*args):
        with db_session() as other:
            other.get(Sentence, seeded["sentence"]).zh = "不同的句子"
            other.commit()
        return []

    monkeypatch.setattr(handoff, "_attachments", change)
    attempt = process(db_session, job)
    with db_session() as session:
        assert session.get(ExportAttempt, attempt).status == "error"
    assert fake.add_calls == 0


def test_remote_add_before_local_commit_failure_recovers_tag_without_duplication(
    client, setup, db_session, monkeypatch
):
    fake, saved = setup
    job = client.post("/api/anki/export", json=payload(client, saved)).json()["job_id"]
    original = handoff._link

    def fail(*args):
        raise RuntimeError("simulated database failure after remote add")

    monkeypatch.setattr(handoff, "_link", fail)
    attempt = process(db_session, job)
    with db_session() as session:
        assert session.get(ExportAttempt, attempt).status == "uncertain"
    monkeypatch.setattr(handoff, "_link", original)
    assert client.post(f"/api/anki/export-attempts/{attempt}/reconcile").json()["status"] == "added"
    assert fake.add_calls == 1


def test_local_removal_during_add_preserves_audit_without_relinking_reused_id(
    client, setup, db_session, monkeypatch
):
    fake, saved = setup
    job = client.post("/api/anki/export", json=payload(client, saved)).json()["job_id"]

    def ac(action, **params):
        reply = fake(action, **params)
        if action == "addNote":
            assert client.delete(f"/api/saved-items/{saved}").status_code == 200
            with db_session() as other:
                other.add(SavedItem(kind="sentence", surface="new card"))
                other.commit()
        return reply

    monkeypatch.setattr(handoff, "ac", ac)
    attempt = process(db_session, job)
    with db_session() as session:
        row = session.get(ExportAttempt, attempt)
        assert row.status == "added" and row.saved_item_id is None
        assert session.query(AnkiLink).one().saved_item_id is None
        assert session.get(SavedItem, saved).surface == "new card"


def test_text_fields_escape_markup_and_duplicate_override_does_not_change_a_chinese_first_field(
    client, setup, db_session
):
    fake, saved = setup
    basic = {**PROFILE, "model": "Basic", "fields": {"Simplified": "Front", "Meaning": "Back"}}
    # A plain sentence without a selected word reading is eligible for a two-field model.
    with db_session() as session:
        item = SavedItem(kind="sentence", surface="你好")
        session.add(item)
        session.commit()
        sentence_id = item.id
    assert client.put("/api/anki/export-profile", json=basic).status_code == 200
    body = payload(client, sentence_id, allow_duplicate=True)
    body["entries"][0]["meaning"] = "<to study & learn>"
    job = client.post("/api/anki/export", json=body).json()["job_id"]
    process(db_session, job)
    note = next(iter(fake.notes.values()))
    assert note["fields"]["Front"] == "你好"
    assert note["fields"]["Back"] == "&lt;to study &amp; learn&gt;"


def test_batch_size_uuid_and_duplicate_row_validation(client, setup):
    _, saved = setup
    body = payload(client, saved)
    assert (
        client.post("/api/anki/export", json={**body, "entries": body["entries"] * 2}).status_code
        == 422
    )
    assert client.post("/api/anki/export", json={**body, "request_uuid": "bad"}).status_code == 422
    assert (
        client.post(
            "/api/anki/export-preview", json={"saved_item_ids": list(range(1, 52))}
        ).status_code
        == 422
    )
    assert (
        client.post(
            "/api/jobs", json={"type": "anki_export", "payload": {"entries": []}}
        ).status_code
        == 400
    )


def test_old_unresolved_attempts_remain_reachable_beyond_history_page_limit(
    client, setup, db_session
):
    _, saved = setup
    job_id = client.post("/api/anki/export", json=payload(client, saved)).json()["job_id"]
    with db_session() as session:
        original = session.scalar(select(ExportAttempt))
        original.status = "uncertain"
        session.get(Job, job_id).status = "done"
        old_id = original.id
        for index in range(25):
            job = Job(type="anki_export", payload={}, status="done")
            session.add(job)
            session.flush()
            session.add(
                ExportAttempt(
                    job_id=job.id,
                    saved_item_id=None,
                    original_saved_item_id=100 + index,
                    export_key="historic-" + str(index),
                    snapshot=copy.deepcopy(original.snapshot),
                    status="added",
                )
            )
        session.commit()
    recent = client.get("/api/anki/exports").json()
    assert len(recent["batches"]) == 20 and recent["next_cursor"]
    assert all(batch["job_id"] != job_id for batch in recent["batches"])
    older = client.get(f"/api/anki/exports?before_job_id={recent['next_cursor']}").json()
    assert any(batch["job_id"] == job_id for batch in older["batches"])
    selected = client.get(f"/api/anki/exports?include_attempt_id={old_id}").json()
    assert selected["batches"][0]["items"][0]["id"] == old_id
    assert selected["batches"][0]["items"][0]["is_latest"]


def test_source_file_replacement_between_preview_and_add_requires_fresh_preview(
    client, setup, seeded, db_session, tmp_path
):
    fake, saved = setup
    source = tmp_path / "a.mp4"
    source.write_bytes(b"original")
    body = payload(client, saved)
    source.write_bytes(b"changed source content")
    assert client.post("/api/anki/export", json=body).status_code == 409
    assert fake.add_calls == 0


def test_traditional_chinese_can_be_the_primary_export_field(client, setup, db_session):
    from app.models import Lexeme

    fake, _ = setup
    with db_session() as session:
        lex = Lexeme(simplified="学习", traditional="學習", pinyin="xue2 xi2", is_dict=True)
        session.add(lex)
        session.flush()
        item = SavedItem(kind="word", lexeme_id=lex.id, surface="學習", selected_meaning="to study")
        session.add(item)
        session.commit()
        saved_id = item.id
    traditional = {
        **PROFILE,
        "model": "Basic",
        "fields": {"Traditional": "Front", "Meaning": "Back"},
    }
    assert client.put("/api/anki/export-profile", json=traditional).status_code == 200
    body = payload(client, saved_id)
    job_id = client.post("/api/anki/export", json=body).json()["job_id"]
    process(db_session, job_id)
    assert next(iter(fake.notes.values()))["fields"]["Front"] == "學習"
