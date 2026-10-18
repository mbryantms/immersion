"""Behavioral checks for source-bound scenes, honest scope and curated Mandarin contrasts."""

# ruff: noqa: F811
from datetime import datetime, timedelta, timezone
from pathlib import Path
from uuid import uuid4

from sqlalchemy import select, text

from app.api import scenes
from app.constructions import CONSTRUCTIONS, VERSION, MeaningQuestion
from app.models import (
    Event,
    GuidedScene,
    KnowledgeState,
    LearningEvidence,
    MediaItem,
    SavedItem,
    SceneQuestion,
    Sentence,
    SentenceIdentity,
    TextTrack,
)
from test_api import client, db_session, seeded  # noqa: F401


def create(client, seeded, **extra):
    response = client.post(
        f"/api/items/{seeded['item']}/scenes",
        json={"sentence_id": seeded["sentence"], "request_uuid": str(uuid4()), **extra},
    )
    assert response.status_code == 200, response.text
    return response.json()


def change(client, scene, action, **extra):
    return client.post(
        f"/api/scenes/{scene['id']}/{action}",
        json={
            "expected_revision": scene["revision"],
            "request_uuid": str(uuid4()),
            **extra,
        },
    )


def to_check(client, scene):
    for stage in ["clarify", "reduce", "check"]:
        response = change(client, scene, "step", stage=stage)
        assert response.status_code == 200, response.text
        scene = response.json()
    return scene


def question(scene):
    return {
        "category": "meaning",
        "prompt": "What is being said?",
        "passage": scene["snapshot"]["lines"][0]["zh"],
        "choices": [
            {"text": "Hello", "explanation": "你好 is a greeting here."},
            {
                "text": "Goodbye",
                "explanation": "This would require a different expression, such as 再见.",
            },
        ],
        "answer": 0,
    }


def test_scene_creation_snapshots_effective_source_and_retries_without_duplicates(
    client, seeded, db_session
):
    with db_session() as session:
        track = session.scalars(select(TextTrack)).first()
        track.offset_ms = 400
        session.commit()
    body = {
        "sentence_id": seeded["sentence"],
        "request_uuid": str(uuid4()),
        "goal": "listen",
        "seconds": 30,
    }
    first = client.post(f"/api/items/{seeded['item']}/scenes", json=body)
    second = client.post(f"/api/items/{seeded['item']}/scenes", json=body)
    assert first.json() == second.json()
    assert first.json()["snapshot"]["t0"] == 400
    assert first.json()["snapshot"]["lines"][0]["zh"] == "你好。"
    with db_session() as session:
        assert session.query(GuidedScene).count() == 1


def test_scene_never_cuts_a_long_cue_or_crosses_tracks(client, seeded, db_session):
    with db_session() as session:
        first = session.get(Sentence, seeded["sentence"])
        session.add(
            Sentence(
                item_id=first.item_id,
                track_id=first.track_id,
                ordinal=1,
                zh="长句。",
                t0_ms=2000,
                t1_ms=80000,
            )
        )
        session.commit()
    scene = create(client, seeded, seconds=30)
    assert len(scene["snapshot"]["lines"]) == 1
    with db_session() as session:
        session.get(Sentence, seeded["sentence"]).t1_ms = 140000
        session.commit()
    response = client.post(
        f"/api/items/{seeded['item']}/scenes",
        json={
            "sentence_id": seeded["sentence"],
            "request_uuid": str(uuid4()),
            "seconds": 120,
        },
    )
    assert response.status_code == 422


def test_steps_require_order_check_and_revision_and_replay_same_request(client, seeded):
    scene = create(client, seeded)
    assert change(client, scene, "step", stage="check").status_code == 409
    body = {"expected_revision": 0, "request_uuid": str(uuid4()), "stage": "clarify"}
    first = client.post(f"/api/scenes/{scene['id']}/step", json=body)
    assert first.status_code == 200
    assert (
        client.post(f"/api/scenes/{scene['id']}/step", json=body).json() == first.json()
    )
    assert change(client, scene, "step", stage="clarify").status_code == 409
    scene = first.json()
    scene = change(client, scene, "step", stage="reduce").json()
    scene = change(client, scene, "step", stage="check").json()
    assert change(client, scene, "step", stage="complete").status_code == 409


def test_hints_and_reflection_remain_self_report_not_word_mastery(
    client, seeded, db_session
):
    scene = to_check(client, create(client, seeded))
    scene = change(client, scene, "hint", kind="translation").json()
    body = {
        "expected_revision": scene["revision"],
        "request_uuid": str(uuid4()),
        "understood": True,
    }
    result = client.post(f"/api/scenes/{scene['id']}/reflection", json=body)
    assert result.status_code == 200
    assert (
        client.post(f"/api/scenes/{scene['id']}/reflection", json=body).json()
        == result.json()
    )
    with db_session() as session:
        evidence = session.query(LearningEvidence).one()
        assert (
            evidence.task == "scene_meaning_reflection"
            and evidence.method == "self_report"
        )
        assert (
            evidence.assistance == "hinted"
            and evidence.scope["prior_same_context_study"]
        )
        assert evidence.lexeme_id is None
        assert session.get(KnowledgeState, seeded["lexeme"]) is None
    assert (
        change(client, result.json(), "reflection", understood=True).status_code == 409
    )


def test_delayed_revisit_is_due_checked_resumable_and_preserves_prior_evidence(
    client, seeded, db_session, monkeypatch
):
    time = datetime.now(timezone.utc)
    monkeypatch.setattr(scenes, "now", lambda: time)
    scene = to_check(client, create(client, seeded))
    scene = change(client, scene, "reflection", understood=False).json()
    scene = change(client, scene, "step", stage="complete").json()
    assert change(client, scene, "revisit").status_code == 409
    time += timedelta(days=1)
    scene = change(client, scene, "revisit").json()
    assert scene["stage"] == "reduce" and scene["support"] == {
        "authored_answer_seen": False
    }
    assert client.get(f"/api/scenes/{scene['id']}").json()["stage"] == "reduce"
    scene = change(client, scene, "step", stage="check").json()
    scene = change(client, scene, "reflection", understood=True).json()
    scene = change(client, scene, "step", stage="complete").json()
    assert datetime.fromisoformat(scene["due_at"]) == time + timedelta(days=3)
    with db_session() as session:
        evidence = session.scalars(
            select(LearningEvidence).order_by(LearningEvidence.id)
        ).all()
        assert (
            len(evidence) == 2
            and not evidence[0].scope["delayed"]
            and evidence[1].scope["delayed"]
        )


def test_question_key_is_hidden_until_answer_and_authorship_is_preserved(
    client, seeded, db_session
):
    scene = create(client, seeded)
    authored = change(
        client, scene, "questions", question=question(scene), reviewed=True
    )
    assert authored.status_code == 200, authored.text
    scene = authored.json()
    assert "answer" not in scene["question"] and "explanations" not in scene["question"]
    assert scene["question"]["externally_validated"] is False
    scene = to_check(client, scene)
    result = change(
        client,
        scene,
        "answer",
        question_id=scene["question"]["id"],
        question_revision=scene["question"]["revision"],
        choice=1,
    )
    assert result.status_code == 200, result.text
    assert result.json()["support"]["answer_feedback"]["correct"] is False
    with db_session() as session:
        evidence = session.query(LearningEvidence).one()
        assert evidence.method == "learner_authored_answer_key"
        assert evidence.scope["answer_key_seen_by_author"]
        assert evidence.score == 0 and evidence.lexeme_id is None


def test_question_must_be_reviewed_strict_and_grounded_in_scene(client, seeded):
    scene = create(client, seeded)
    for payload in [
        {"question": question(scene), "reviewed": False},
        {"question": {**question(scene), "answer": 3}, "reviewed": True},
        {"question": {**question(scene), "unknown": True}, "reviewed": True},
        {"question": {**question(scene), "passage": "捏造的句子。"}, "reviewed": True},
        {
            "question": {
                **question(scene),
                "choices": [question(scene)["choices"][0]] * 2,
            },
            "reviewed": True,
        },
    ]:
        assert change(client, scene, "questions", **payload).status_code == 422


def test_reporting_suspends_question_without_deleting_history_or_blocking_reflection(
    client, seeded, db_session
):
    scene = create(client, seeded)
    scene = change(
        client, scene, "questions", question=question(scene), reviewed=True
    ).json()
    q = scene["question"]
    scene = to_check(client, scene)
    scene = change(
        client,
        scene,
        "report-question",
        question_id=q["id"],
        reason="Ambiguous context",
    ).json()
    assert scene["question"] is None
    assert (
        change(
            client,
            scene,
            "answer",
            question_id=q["id"],
            question_revision=q["revision"],
            choice=0,
        ).status_code
        == 409
    )
    assert change(client, scene, "reflection", understood=False).status_code == 200
    with db_session() as session:
        assert session.get(SceneQuestion, q["id"]).status == "suspended"
        assert (
            session.query(Event).filter_by(type="scene_question_suspended").count() == 1
        )


def test_source_correction_or_media_change_blocks_old_audio_and_keyed_grading(
    client, seeded, db_session
):
    scene = create(client, seeded)
    scene = change(
        client, scene, "questions", question=question(scene), reviewed=True
    ).json()
    q = scene["question"]
    scene = to_check(client, scene)
    with db_session() as session:
        session.get(MediaItem, seeded["item"]).fingerprint = "changed"
        session.get(Sentence, seeded["sentence"]).zh = "再见。"
        session.commit()
    current = client.get(f"/api/scenes/{scene['id']}").json()
    assert not current["source_current"] and current["stream_url"] is None
    assert current["snapshot"]["lines"][0]["zh"] == "你好。"
    assert (
        change(
            client,
            current,
            "answer",
            question_id=q["id"],
            question_revision=q["revision"],
            choice=0,
        ).status_code
        == 409
    )
    assert change(client, current, "reflection", understood=False).status_code == 200


def test_adding_question_during_hidden_attempt_is_rejected(client, seeded):
    scene = create(client, seeded)
    scene = change(client, scene, "step", stage="clarify").json()
    scene = change(client, scene, "step", stage="reduce").json()
    assert (
        change(
            client, scene, "questions", question=question(scene), reviewed=True
        ).status_code
        == 409
    )


def test_corrected_timing_revision_is_detected(client, seeded, db_session):
    scene = create(client, seeded)
    with db_session() as session:
        session.add(
            SentenceIdentity(
                id=seeded["sentence"], item_id=seeded["item"], source={}, revision=1
            )
        )
        session.commit()
    assert client.get(f"/api/scenes/{scene['id']}").json()["source_current"] is False


def test_budget_is_soft_counts_archived_intake_and_vocabulary_preserves_beginner_words(
    client, seeded, db_session
):
    scene = create(client, seeded)
    assert client.get("/api/mining/budget").json()["remaining"] == 5
    assert (
        client.put("/api/mining/budget", json={"daily_word_budget": 1}).status_code
        == 200
    )
    vocabulary = client.get(f"/api/scenes/{scene['id']}/vocabulary").json()
    assert (
        vocabulary["items"][0]["surface"] == "你好" and vocabulary["suggested_max"] == 1
    )
    with db_session() as session:
        session.add(
            SavedItem(
                kind="word", lexeme_id=seeded["lexeme"], surface="你好", archived=True
            )
        )
        session.commit()
    assert client.get("/api/mining/budget").json()["remaining"] == 0
    assert (
        client.get(f"/api/scenes/{scene['id']}/vocabulary").json()["suggested_max"] == 0
    )
    assert (
        client.post(
            "/api/saved-items",
            json={"kind": "word", "lexeme_id": seeded["lexeme"], "surface": "你好"},
        ).status_code
        == 200
    )
    assert (
        client.put("/api/mining/budget", json={"daily_word_budget": -1}).status_code
        == 422
    )


def test_curated_bank_has_distinct_valid_keys_explanations_and_mandarin_scope(client):
    assert len(CONSTRUCTIONS) == 12
    assert {entry["question"].answer for entry in CONSTRUCTIONS.values()} == {0, 1}
    assert {
        "agent_patient",
        "negation",
        "aspect",
        "result",
        "comparison",
        "paraphrase",
    } <= {entry["question"].category for entry in CONSTRUCTIONS.values()}
    payload = client.get("/api/constructions").json()
    assert all("answer" not in item["question"] for item in payload["items"])
    for key, entry in CONSTRUCTIONS.items():
        question = MeaningQuestion.model_validate(entry["question"].model_dump())
        response = client.post(
            f"/api/constructions/{key}/answer",
            json={
                "choice": question.answer,
                "version": VERSION,
                "request_uuid": str(uuid4()),
            },
        )
        assert response.json()["correct"] is True
        assert len(response.json()["explanations"]) == len(question.choices)


def test_construction_retry_and_report_suspend_and_restore_preserve_original_result(
    client, db_session
):
    body = {
        "choice": 0,
        "hint_used": True,
        "version": VERSION,
        "request_uuid": str(uuid4()),
    }
    first = client.post("/api/constructions/negation/answer", json=body)
    assert (
        client.post("/api/constructions/negation/answer", json=body).json()
        == first.json()
    )
    assert (
        client.post(
            "/api/constructions/negation/report",
            json={
                "reason": "Check this contrast",
                "version": VERSION,
                "request_uuid": str(uuid4()),
            },
        ).status_code
        == 200
    )
    assert (
        client.post(
            "/api/constructions/negation/answer",
            json={**body, "request_uuid": str(uuid4())},
        ).status_code
        == 409
    )
    assert (
        client.post(
            "/api/constructions/negation/restore",
            json={"reviewed": True, "version": VERSION, "request_uuid": str(uuid4())},
        ).status_code
        == 200
    )
    with db_session() as session:
        evidence = session.query(LearningEvidence).one()
        assert evidence.assistance == "hinted" and evidence.scope["practice_only"]
        assert (
            evidence.task == "construction_meaning_choice"
            and evidence.lexeme_id is None
        )


def test_scene_migration_preserves_learner_data_and_backup(tmp_path, monkeypatch):
    from alembic import command
    from alembic.config import Config
    from sqlalchemy.orm import Session
    from app import db
    from app.config import settings

    monkeypatch.setattr(settings, "data_dir", tmp_path)
    cfg = Config(str(Path(__file__).parents[1] / "src/alembic.ini"))
    cfg.set_main_option(
        "script_location", str(Path(__file__).parents[1] / "src/app/migrations")
    )
    command.upgrade(cfg, "d4e6f8a0b2c4")
    engine = db.make_engine()
    with Session(engine) as session:
        original = Event(type="original", data={"preserve": True})
        session.add(original)
        session.flush()
        session.execute(
            text(
                "INSERT INTO learning_evidence(event_id,ts,task,method,assistance,score,scope) VALUES(:id,CURRENT_TIMESTAMP,'reading_recall','self_report','unknown',1,'{}')"
            ),
            {"id": original.id},
        )
        session.commit()
    db.upgrade_db()
    with Session(engine) as session:
        assert session.query(Event).one().data == {"preserve": True}
        assert session.query(LearningEvidence).one().valid_for_summary
        assert session.query(LearningEvidence).one().score == 1
        assert session.query(GuidedScene).count() == 0
        assert session.query(SceneQuestion).count() == 0
    assert list((tmp_path / "backups").glob("*.db"))


def test_stale_exercise_version_cannot_grade_current_key(client):
    assert (
        client.post(
            "/api/constructions/result/answer",
            json={"choice": 0, "version": "old", "request_uuid": str(uuid4())},
        ).status_code
        == 409
    )
    assert (
        client.post(
            "/api/constructions/result/report",
            json={
                "reason": "Old prompt",
                "version": "old",
                "request_uuid": str(uuid4()),
            },
        ).status_code
        == 409
    )
    assert (
        client.post(
            "/api/constructions/result/restore",
            json={"reviewed": True, "version": "old", "request_uuid": str(uuid4())},
        ).status_code
        == 409
    )


def test_concurrent_step_only_advances_once(client, seeded, db_session):
    from concurrent.futures import ThreadPoolExecutor
    from fastapi.testclient import TestClient
    from app.main import app

    scene = create(client, seeded)

    def submit(_):
        return (
            TestClient(app)
            .post(
                f"/api/scenes/{scene['id']}/step",
                json={
                    "expected_revision": 0,
                    "stage": "clarify",
                    "request_uuid": str(uuid4()),
                },
            )
            .status_code
        )

    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(submit, range(2)))
    assert sorted(results) == [200, 409]
    with db_session() as session:
        assert session.query(Event).filter_by(type="scene_step").count() == 1
        assert session.get(GuidedScene, scene["id"]).revision == 1


def test_repeat_construction_results_are_marked_practice_not_new_first_attempts(
    client, db_session
):
    for _ in range(2):
        response = client.post(
            "/api/constructions/negation/answer",
            json={"choice": 0, "version": VERSION, "request_uuid": str(uuid4())},
        )
        assert response.status_code == 200
    with db_session() as session:
        evidence = session.scalars(
            select(LearningEvidence).order_by(LearningEvidence.id)
        ).all()
        assert (
            evidence[0].scope["first_attempt"]
            and not evidence[1].scope["first_attempt"]
        )


def test_reporting_invalidates_past_averages_but_retains_original_attempts(
    client, db_session
):
    client.post(
        "/api/constructions/negation/answer",
        json={
            "choice": CONSTRUCTIONS["negation"]["question"].answer,
            "version": VERSION,
            "request_uuid": str(uuid4()),
        },
    )
    assert (
        client.get("/api/stats/dashboard").json()["practice_evidence"][0]["mean_score"]
        == 1
    )
    client.post(
        "/api/constructions/negation/report",
        json={"reason": "Ambiguous", "version": VERSION, "request_uuid": str(uuid4())},
    )
    stats = client.get("/api/stats/dashboard").json()
    assert stats["excluded_question_results"] == 1 and stats["practice_evidence"] == []
    with db_session() as session:
        evidence = session.query(LearningEvidence).one()
        assert evidence.score == 1 and not evidence.valid_for_summary
        assert (
            session.query(Event)
            .filter_by(type="construction_answer")
            .one()
            .data["response"]["correct"]
        )
    client.post(
        "/api/constructions/negation/restore",
        json={"reviewed": True, "version": VERSION, "request_uuid": str(uuid4())},
    )
    assert client.get("/api/stats/dashboard").json()["practice_evidence"] == []


def test_reported_scene_grade_requires_reflection_and_leaves_immutable_evidence(
    client, seeded, db_session
):
    scene = create(client, seeded)
    scene = change(
        client, scene, "questions", question=question(scene), reviewed=True
    ).json()
    q = scene["question"]
    scene = to_check(client, scene)
    scene = change(
        client,
        scene,
        "answer",
        question_id=q["id"],
        question_revision=q["revision"],
        choice=0,
    ).json()
    scene = change(
        client, scene, "report-question", question_id=q["id"], reason="Ambiguous"
    ).json()
    assert scene["support"]["checked"] is False
    assert change(client, scene, "step", stage="complete").status_code == 409
    assert change(client, scene, "reflection", understood=False).status_code == 200
    with db_session() as session:
        evidence = session.scalars(
            select(LearningEvidence).where(
                LearningEvidence.method == "learner_authored_answer_key"
            )
        ).one()
        assert evidence.score == 1 and not evidence.valid_for_summary


def test_due_scenes_remain_visible_ahead_of_many_unfinished_scenes(
    client, seeded, db_session
):
    scene = create(client, seeded)
    with db_session() as session:
        original = session.get(GuidedScene, scene["id"])
        original.stage = "complete"
        original.due_at = datetime.now(timezone.utc) - timedelta(days=1)
        for _ in range(31):
            session.add(
                GuidedScene(
                    request_uuid=str(uuid4()),
                    item_id=seeded["item"],
                    goal="read",
                    snapshot=original.snapshot,
                    stage="watch",
                    revision=0,
                    support={},
                    revisits=0,
                )
            )
        session.commit()
    items = client.get("/api/scenes").json()["items"]
    assert len(items) == 30 and items[0]["id"] == scene["id"] and items[0]["due"]


def test_scene_rejects_cues_beyond_known_media_duration(client, seeded, db_session):
    with db_session() as session:
        session.get(MediaItem, seeded["item"]).duration_ms = 500
        session.commit()
    response = client.post(
        f"/api/items/{seeded['item']}/scenes",
        json={"sentence_id": seeded["sentence"], "request_uuid": str(uuid4())},
    )
    assert response.status_code == 422


def test_suspension_preserves_context_review_evidence_and_daily_intake(
    client, seeded, db_session
):
    saved = client.post(
        "/api/saved-items",
        json={
            "kind": "word",
            "lexeme_id": seeded["lexeme"],
            "surface": "你好",
            "sentence_id": seeded["sentence"],
            "selected_meaning": "hello",
        },
    ).json()
    client.post(
        f"/api/review/{saved['id']}/outcome",
        json={"result": "pass", "task": "reading_recall", "request_uuid": str(uuid4())},
    )
    before = client.get("/api/saved-items").json()["items"][0]
    assert (
        client.patch(
            f"/api/saved-items/{saved['id']}", json={"archived": True}
        ).status_code
        == 200
    )
    assert client.get("/api/saved-items").json()["items"] == []
    paused = client.get("/api/saved-items?archived=true").json()["items"][0]
    assert (
        paused["archived"]
        and paused["review"] == before["review"]
        and paused["contexts"] == before["contexts"]
    )
    assert client.get("/api/mining/budget").json()["used"] == 1
    assert (
        client.patch(
            f"/api/saved-items/{saved['id']}", json={"archived": False}
        ).status_code
        == 200
    )
    restored = client.get("/api/saved-items").json()["items"][0]
    assert restored["id"] == before["id"] and restored["selected_meaning"] == "hello"
    with db_session() as session:
        assert session.query(LearningEvidence).count() == 1
        assert (
            session.query(Event)
            .filter(Event.type.in_(("saved_suspended", "saved_resumed")))
            .count()
            == 2
        )
