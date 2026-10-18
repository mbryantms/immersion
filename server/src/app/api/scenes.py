"""Local guided learning. Source snapshots, explicit assistance and scoped grades."""

from datetime import datetime, timedelta, timezone
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException
from fastapi.encoders import jsonable_encoder
from pydantic import BaseModel, Field
from sqlalchemy import case, func, or_, select, update
from sqlalchemy.orm import Session

from ..constructions import CONSTRUCTIONS, VERSION, MeaningQuestion
from ..db import get_session
from ..models import (
    Event,
    GuidedScene,
    KnowledgeState,
    LearningEvidence,
    Lexeme,
    MediaItem,
    MediaRoot,
    SavedItem,
    SceneQuestion,
    Sentence,
    SentenceIdentity,
    Setting,
)
from ..timing import effective_times
from .library import stream_url

router = APIRouter()
STAGES = ["watch", "clarify", "reduce", "check", "complete"]


def now():
    return datetime.now(timezone.utc)


def aware(value):
    return (
        value.replace(tzinfo=timezone.utc) if value and value.tzinfo is None else value
    )


def question_public(question):
    return {
        "category": question.category,
        "prompt": question.prompt,
        "passage": question.passage,
        "choices": [choice.text for choice in question.choices],
    }


def source_current(session, scene):
    item = session.get(MediaItem, scene.item_id)
    if (
        item is None
        or item.fingerprint != scene.snapshot.get("fingerprint")
        or (item.duration_ms and scene.snapshot["t1"] > item.duration_ms)
    ):
        return False
    for line in scene.snapshot["lines"]:
        sentence = session.get(Sentence, line["id"])
        identity = session.get(SentenceIdentity, line["id"])
        if (
            sentence is None
            or sentence.zh != line["zh"]
            or (identity.revision if identity else 0) != line["revision"]
        ):
            return False
        if effective_times(session, sentence) != (line["t0"], line["t1"]):
            return False
    return True


def scene_payload(session, scene):
    item = session.get(MediaItem, scene.item_id)
    root = session.get(MediaRoot, item.root_id) if item else None
    current = source_current(session, scene)
    question = session.scalar(
        select(SceneQuestion)
        .where(SceneQuestion.scene_id == scene.id, SceneQuestion.status == "active")
        .order_by(SceneQuestion.id.desc())
        .limit(1)
    )
    return {
        "id": scene.id,
        "item_id": scene.item_id,
        "goal": scene.goal,
        "stage": scene.stage,
        "revision": scene.revision,
        "snapshot": scene.snapshot,
        "support": scene.support,
        "revisits": scene.revisits,
        "due_at": scene.due_at,
        "completed_at": scene.completed_at,
        "source_current": current,
        "stream_url": stream_url(item, root.slug)
        if current and item.available and root
        else None,
        "question": {
            "id": question.id,
            "revision": question.revision,
            **question_public(MeaningQuestion.model_validate(question.body)),
            "provenance": "learner_authored_reviewed",
            "externally_validated": False,
        }
        if question
        else None,
    }


class Request(BaseModel):
    request_uuid: str = Field(min_length=8, max_length=64, pattern=r"^[A-Za-z0-9-]+$")


class CreateScene(Request):
    sentence_id: int = Field(gt=0)
    goal: Literal["read", "listen"] = "listen"
    seconds: int = Field(default=60, ge=15, le=120)


@router.post("/items/{item_id}/scenes")
def create_scene(
    item_id: int, body: CreateScene, session: Session = Depends(get_session)
):
    # Acquire the SQLite writer lock before request replay / snapshot selection.
    session.execute(
        update(MediaItem).where(MediaItem.id == item_id).values(ready=MediaItem.ready)
    )
    existing = session.scalar(
        select(GuidedScene).where(GuidedScene.request_uuid == body.request_uuid)
    )
    if existing:
        if existing.item_id != item_id:
            raise HTTPException(409, "This request belongs to another item")
        return scene_payload(session, existing)
    item = session.get(MediaItem, item_id)
    first = session.get(Sentence, body.sentence_id)
    if item is None or first is None or first.item_id != item_id:
        raise HTTPException(404, "Source sentence not found in this item")
    if not item.ready:
        raise HTTPException(409, "Wait until transcript processing finishes")
    first_t0, _ = effective_times(session, first)
    lines = []
    for sentence in session.scalars(
        select(Sentence)
        .where(
            Sentence.item_id == item_id,
            Sentence.track_id == first.track_id,
            Sentence.ordinal >= first.ordinal,
        )
        .order_by(Sentence.ordinal)
        .limit(20)
    ):
        t0, t1 = effective_times(session, sentence)
        if t0 < first_t0 or t1 <= t0:
            continue
        if t1 > first_t0 + body.seconds * 1000 or (
            item.duration_ms and t1 > item.duration_ms
        ):
            break  # Never cut the answer off mid-cue.
        identity = session.get(SentenceIdentity, sentence.id)
        lines.append(
            {
                "id": sentence.id,
                "zh": sentence.zh,
                "en": sentence.en,
                "translation_source": sentence.en_source,
                "t0": t0,
                "t1": t1,
                "revision": identity.revision if identity else 0,
                "words": (sentence.analysis or {}).get("words", []),
            }
        )
    if not lines:
        raise HTTPException(
            422,
            "This cue is too long or has invalid timing; choose another start or a longer scene",
        )
    scene = GuidedScene(
        request_uuid=body.request_uuid,
        item_id=item_id,
        goal=body.goal,
        snapshot={
            "title": item.title,
            "fingerprint": item.fingerprint,
            "kind": item.kind,
            "t0": min(line["t0"] for line in lines),
            "t1": max(line["t1"] for line in lines),
            "lines": lines,
        },
        stage="watch",
        revision=0,
        support={},
        revisits=0,
    )
    session.add(scene)
    session.commit()
    return scene_payload(session, scene)


@router.get("/scenes")
def list_scenes(session: Session = Depends(get_session)):
    rows = session.scalars(
        select(GuidedScene)
        .order_by(
            case(
                ((GuidedScene.stage == "complete") & (GuidedScene.due_at <= now()), 0),
                (GuidedScene.stage != "complete", 1),
                else_=2,
            ),
            GuidedScene.due_at,
            GuidedScene.created_at.desc(),
        )
        .limit(30)
    ).all()
    return {
        "items": [
            {
                "id": row.id,
                "item_id": row.item_id,
                "title": row.snapshot["title"],
                "goal": row.goal,
                "stage": row.stage,
                "revision": row.revision,
                "due_at": row.due_at,
                "due": bool(row.due_at and aware(row.due_at) <= now()),
                "duration_ms": row.snapshot["t1"] - row.snapshot["t0"],
            }
            for row in rows
        ]
    }


@router.get("/scenes/{scene_id}")
def get_scene(scene_id: int, session: Session = Depends(get_session)):
    scene = session.get(GuidedScene, scene_id)
    if scene is None:
        raise HTTPException(404)
    return scene_payload(session, scene)


class Change(Request):
    expected_revision: int = Field(ge=0)


def claim(session, scene_id, body, action):
    session.execute(
        update(GuidedScene)
        .where(GuidedScene.id == scene_id)
        .values(revision=GuidedScene.revision)
    )
    key = f"scene:{scene_id}:{action}:{body.request_uuid}"
    previous = session.scalar(select(Event).where(Event.client_uuid == key))
    if previous:
        current = session.get(GuidedScene, scene_id)
        return (
            None,
            key,
            {
                **jsonable_encoder(scene_payload(session, current)),
                **previous.data["response"],
            },
        )
    scene = session.get(GuidedScene, scene_id, populate_existing=True)
    if scene is None:
        raise HTTPException(404)
    if scene.revision != body.expected_revision:
        raise HTTPException(
            409, "This scene changed in another tab. Reload before continuing."
        )
    scene.revision += 1
    return scene, key, None


def finish_request(session, scene, key, action, data=None):
    session.flush()
    response = jsonable_encoder(scene_payload(session, scene))
    session.add(
        Event(
            type=action,
            item_id=scene.item_id,
            client_uuid=key,
            study_mode=scene.goal,
            data={
                "scene_id": scene.id,
                **(data or {}),
                "response": {
                    name: value
                    for name, value in response.items()
                    if name not in ("snapshot", "stream_url", "source_current")
                },
            },
        )
    )
    session.commit()
    return response


class Step(Change):
    stage: Literal["clarify", "reduce", "check", "complete"]


@router.post("/scenes/{scene_id}/step")
def advance(scene_id: int, body: Step, session: Session = Depends(get_session)):
    scene, key, replay = claim(session, scene_id, body, "step")
    if replay is not None:
        return replay
    if (
        scene.stage == "complete"
        or STAGES.index(body.stage) != STAGES.index(scene.stage) + 1
    ):
        raise HTTPException(409, "Complete the current step before moving on")
    if body.stage == "complete":
        if not scene.support.get("checked"):
            raise HTTPException(
                409, "Answer or reflect on the meaning before completing this scene"
            )
        scene.completed_at = now()
        scene.due_at = now() + timedelta(days=[1, 3, 7][min(scene.revisits, 2)])
    scene.stage = body.stage
    return finish_request(session, scene, key, "scene_step")


class Hint(Change):
    kind: Literal["text", "translation", "replay"]


@router.post("/scenes/{scene_id}/hint")
def hint(scene_id: int, body: Hint, session: Session = Depends(get_session)):
    scene, key, replay = claim(session, scene_id, body, "hint")
    if replay is not None:
        return replay
    if scene.stage == "complete":
        raise HTTPException(409, "Start a due revisit to practise this scene again")
    name = f"{scene.stage}_{body.kind}"
    scene.support = {**scene.support, name: scene.support.get(name, 0) + 1}
    return finish_request(session, scene, key, "scene_hint", {"kind": body.kind})


def assistance(scene):
    hinted = any(
        scene.support.get(f"{stage}_{kind}")
        for stage in ("reduce", "check")
        for kind in ("text", "translation")
    )
    return "hinted" if hinted else "none_reported"


class Reflection(Change):
    understood: bool


@router.post("/scenes/{scene_id}/reflection")
def reflect(scene_id: int, body: Reflection, session: Session = Depends(get_session)):
    scene, key, replay = claim(session, scene_id, body, "reflection")
    if replay is not None:
        return replay
    if scene.stage != "check" or scene.support.get("checked"):
        raise HTTPException(
            409, "The meaning check is not available or was already recorded"
        )
    _record_performance(
        session,
        scene,
        key,
        "scene_meaning_reflection",
        "self_report",
        int(body.understood),
        {
            "limitation": "Self-report on practiced material, not an objective comprehension test"
        },
    )
    scene.support = {**scene.support, "checked": True, "reflection": body.understood}
    return finish_request(session, scene, key, "scene_reflection")


def _record_performance(session, scene, key, task, method, score, scope):
    event = Event(
        type="guided_practice",
        item_id=scene.item_id,
        study_mode=scene.goal,
        client_uuid=key + ":evidence",
        data={"scene_id": scene.id, "task": task, "score": score, **scope},
    )
    session.add(event)
    session.flush()
    session.add(
        LearningEvidence(
            event_id=event.id,
            ts=now(),
            task=task,
            method=method,
            assistance=assistance(scene),
            score=score,
            scope={
                "scene_id": scene.id,
                "item_id": scene.item_id,
                "skill": scene.goal,
                "support": scene.support,
                "prior_same_context_study": True,
                "delayed": scene.revisits > 0,
                "source_current": source_current(session, scene),
                **scope,
            },
        )
    )


class AuthorQuestion(Change):
    question: MeaningQuestion
    reviewed: Literal[True]


@router.post("/scenes/{scene_id}/questions")
def author_question(
    scene_id: int, body: AuthorQuestion, session: Session = Depends(get_session)
):
    scene, key, replay = claim(session, scene_id, body, "author")
    if replay is not None:
        return replay
    if (
        not source_current(session, scene)
        or scene.stage not in ("watch", "clarify")
        or scene.support.get("checked")
    ):
        raise HTTPException(
            409, "Create a new scene for the current source before adding a question"
        )
    # Require the exact source evidence, not an invented example supplied as a passage.
    if body.question.passage not in [line["zh"] for line in scene.snapshot["lines"]]:
        raise HTTPException(
            422, "Choose an exact source sentence as the question evidence"
        )
    for previous in session.scalars(
        select(SceneQuestion).where(
            SceneQuestion.scene_id == scene_id, SceneQuestion.status == "active"
        )
    ):
        previous.status = "replaced"
    session.add(
        SceneQuestion(
            scene_id=scene_id,
            body=body.question.model_dump(),
            revision=scene.revision,
            status="active",
        )
    )
    scene.support = {**scene.support, "authored_answer_seen": True}
    return finish_request(session, scene, key, "scene_question_authored")


class Answer(Change):
    question_id: int = Field(gt=0)
    question_revision: int = Field(gt=0)
    choice: int = Field(ge=0, le=3)


@router.post("/scenes/{scene_id}/answer")
def answer(scene_id: int, body: Answer, session: Session = Depends(get_session)):
    scene, key, replay = claim(session, scene_id, body, "answer")
    if replay is not None:
        return replay
    question = session.get(SceneQuestion, body.question_id)
    if scene.stage != "check" or scene.support.get("checked"):
        raise HTTPException(
            409, "The meaning check is not available or was already recorded"
        )
    if (
        not question
        or question.scene_id != scene_id
        or question.status != "active"
        or question.revision != body.question_revision
    ):
        raise HTTPException(
            409, "This question changed or was suspended. Reload the scene"
        )
    if not source_current(session, scene):
        raise HTTPException(
            409, "The source changed. Use reflection or create a new scene"
        )
    if scene.goal == "listen" and not scene_payload(session, scene)["stream_url"]:
        raise HTTPException(
            409, "Audio is unavailable. Use the reflection option instead"
        )
    parsed = MeaningQuestion.model_validate(question.body)
    if body.choice >= len(parsed.choices):
        raise HTTPException(422, "Choose one of the available answers")
    correct = body.choice == parsed.answer
    feedback = {
        "correct": correct,
        "answer": parsed.answer,
        "choice": body.choice,
        "explanations": [choice.explanation for choice in parsed.choices],
        "provenance": "learner_authored_reviewed",
    }
    _record_performance(
        session,
        scene,
        key,
        "scene_meaning_choice",
        "learner_authored_answer_key",
        int(correct),
        {
            "question_id": question.id,
            "question_revision": question.revision,
            "answer_key_seen_by_author": bool(
                scene.support.get("authored_answer_seen")
            ),
            "limitation": "Local learner-authored key; not externally validated or an unseen-context test",
        },
    )
    scene.support = {**scene.support, "checked": True, "answer_feedback": feedback}
    return finish_request(session, scene, key, "scene_answer")


class Report(Change):
    question_id: int = Field(gt=0)
    reason: str = Field(min_length=1, max_length=1000)


@router.post("/scenes/{scene_id}/report-question")
def report_question(
    scene_id: int, body: Report, session: Session = Depends(get_session)
):
    scene, key, replay = claim(session, scene_id, body, "report")
    if replay is not None:
        return replay
    question = session.get(SceneQuestion, body.question_id)
    if question is None or question.scene_id != scene_id:
        raise HTTPException(404)
    question.status = "suspended"
    session.execute(
        update(LearningEvidence)
        .where(
            LearningEvidence.scope["question_id"].as_integer() == question.id,
            LearningEvidence.method == "learner_authored_answer_key",
        )
        .values(valid_for_summary=False)
        .execution_options(synchronize_session=False)
    )
    scene.support = {
        **scene.support,
        "checked": False,
        "question_reported": question.id,
    }
    return finish_request(
        session,
        scene,
        key,
        "scene_question_suspended",
        {"question_id": question.id, "reason": body.reason},
    )


@router.post("/scenes/{scene_id}/revisit")
def revisit(scene_id: int, body: Change, session: Session = Depends(get_session)):
    scene, key, replay = claim(session, scene_id, body, "revisit")
    if replay is not None:
        return replay
    if scene.stage != "complete" or not scene.due_at or aware(scene.due_at) > now():
        raise HTTPException(409, "This scene is not due for a delayed revisit yet")
    scene.stage, scene.due_at, scene.completed_at = "reduce", None, None
    scene.revisits += 1
    scene.support = {
        "authored_answer_seen": scene.support.get("authored_answer_seen", False)
    }
    return finish_request(session, scene, key, "scene_revisit")


class Budget(BaseModel):
    daily_word_budget: int = Field(default=5, ge=0, le=30)


@router.get("/mining/budget")
def mining_budget(session: Session = Depends(get_session)):
    setting = session.get(Setting, "mining_budget")
    budget = Budget.model_validate(setting.value if setting else {}).daily_word_budget
    midnight = now().replace(hour=0, minute=0, second=0, microsecond=0)
    used = (
        session.scalar(
            select(func.count())
            .select_from(SavedItem)
            .where(SavedItem.kind == "word", SavedItem.created_at >= midnight)
        )
        or 0
    )
    return {
        "daily_word_budget": budget,
        "used": used,
        "remaining": max(0, budget - used),
        "timezone": "UTC",
        "soft_limit": True,
    }


@router.put("/mining/budget")
def set_budget(body: Budget, session: Session = Depends(get_session)):
    session.merge(Setting(key="mining_budget", value=body.model_dump()))
    session.commit()
    return mining_budget(session)


@router.get("/scenes/{scene_id}/vocabulary")
def vocabulary(scene_id: int, session: Session = Depends(get_session)):
    scene = session.get(GuidedScene, scene_id)
    if scene is None:
        raise HTTPException(404)
    words = {}
    for line in scene.snapshot["lines"]:
        for word in line["words"]:
            if word.get("type") == "zh" and word.get("lex"):
                entry = words.setdefault(
                    word["lex"], {**word, "sentence_id": line["id"], "occurrences": 0}
                )
                entry["occurrences"] += 1
    from .sentences import _lexeme_payload

    out = []
    for lex in session.scalars(
        select(Lexeme).where(Lexeme.id.in_(words), Lexeme.is_dict.is_(True))
    ):
        state = session.get(KnowledgeState, lex.id)
        if state and state.state in ("known", "ignored", "familiar"):
            continue
        entry = words[lex.id]
        out.append(
            {
                **_lexeme_payload(session, lex),
                "surface": entry["t"],
                "sentence_id": entry["sentence_id"],
                "occurrences": entry["occurrences"],
            }
        )
    out.sort(key=lambda word: (-word["occurrences"], word["lexeme_id"]))
    return {
        "items": out[:8],
        "suggested_max": min(3, mining_budget(session)["remaining"]),
        "source_current": source_current(session, scene),
    }


@router.get("/constructions")
def constructions(session: Session = Depends(get_session)):
    suspended = session.get(Setting, "suspended_constructions")
    hidden = set((suspended.value or {}).get("ids", [])) if suspended else set()
    return {
        "version": VERSION,
        "items": [
            {
                "id": value["id"],
                "title": value["title"],
                "note": value["note"],
                "examples": value["examples"],
                "suspended": value["id"] in hidden,
                "question": question_public(value["question"]),
            }
            for value in CONSTRUCTIONS.values()
        ],
    }


@router.get("/constructions/{construction_id}/examples")
def construction_examples(
    construction_id: str, session: Session = Depends(get_session)
):
    construction = CONSTRUCTIONS.get(construction_id)
    if construction is None:
        raise HTTPException(404)
    markers = [variant for group in construction["markers"] for variant in group]
    rows = session.scalars(
        select(Sentence)
        .where(
            or_(*[Sentence.zh.contains(marker, autoescape=True) for marker in markers])
        )
        .order_by(Sentence.id.desc())
        .limit(6)
    ).all()
    return {
        "candidate_matches": True,
        "items": [
            {
                "sentence_id": row.id,
                "item_id": row.item_id,
                "zh": row.zh,
                "en": row.en,
                "t0_ms": effective_times(session, row)[0],
            }
            for row in rows
        ],
    }


class ConstructionAnswer(Request):
    version: str = Field(max_length=80)
    choice: int = Field(ge=0, le=3)
    hint_used: bool = False


@router.post("/constructions/{construction_id}/answer")
def construction_answer(
    construction_id: str,
    body: ConstructionAnswer,
    session: Session = Depends(get_session),
):
    # Serialize on a settings row so retries and suspension cannot race a grade.
    from sqlalchemy.dialects.sqlite import insert

    session.execute(
        insert(Setting)
        .values(key="suspended_constructions", value={"ids": []})
        .on_conflict_do_nothing()
    )
    key = f"construction:{construction_id}:{body.request_uuid}"
    previous = session.scalar(select(Event).where(Event.client_uuid == key))
    if previous:
        return previous.data["response"]
    construction = CONSTRUCTIONS.get(construction_id)
    suspended = session.get(Setting, "suspended_constructions")
    if construction is None:
        raise HTTPException(404)
    if construction_id in suspended.value.get("ids", []):
        raise HTTPException(409, "This exercise is suspended")
    if body.version != VERSION:
        raise HTTPException(409, "Exercise version changed. Reload before answering")
    question = construction["question"]
    if body.choice >= len(question.choices):
        raise HTTPException(422, "Choose an available answer")
    prior = session.scalar(
        select(Event.id)
        .where(
            Event.type == "construction_answer",
            Event.data["construction_id"].as_string() == construction_id,
        )
        .limit(1)
    )
    response = {
        "correct": body.choice == question.answer,
        "answer": question.answer,
        "choice": body.choice,
        "explanations": [choice.explanation for choice in question.choices],
        "version": VERSION,
        "scope": "curated_construction_practice",
    }
    event = Event(
        type="construction_answer",
        client_uuid=key,
        study_mode="read",
        data={"construction_id": construction_id, "response": response},
    )
    session.add(event)
    session.flush()
    session.add(
        LearningEvidence(
            event_id=event.id,
            ts=now(),
            task="construction_meaning_choice",
            method="curated_answer_key",
            assistance="hinted" if body.hint_used else "none_reported",
            score=int(response["correct"]),
            scope={
                "construction_id": construction_id,
                "version": VERSION,
                "category": question.category,
                "practice_only": True,
                "first_attempt": prior is None,
                "limitation": "Curated example reading practice; not comprehension of a library scene or an unseen benchmark",
            },
        )
    )
    session.commit()
    return response


class ConstructionReport(Request):
    version: str = Field(max_length=80)
    reason: str = Field(min_length=1, max_length=1000)


@router.post("/constructions/{construction_id}/report")
def construction_report(
    construction_id: str,
    body: ConstructionReport,
    session: Session = Depends(get_session),
):
    if construction_id not in CONSTRUCTIONS:
        raise HTTPException(404)
    if body.version != VERSION:
        raise HTTPException(409, "Exercise version changed. Reload first")
    from sqlalchemy.dialects.sqlite import insert

    session.execute(
        insert(Setting)
        .values(key="suspended_constructions", value={"ids": []})
        .on_conflict_do_nothing()
    )
    key = f"construction-report:{construction_id}:{body.request_uuid}"
    if session.scalar(select(Event.id).where(Event.client_uuid == key)):
        return {"suspended": True}
    session.execute(
        update(LearningEvidence)
        .where(
            LearningEvidence.scope["construction_id"].as_string() == construction_id,
            LearningEvidence.scope["version"].as_string() == VERSION,
            LearningEvidence.method == "curated_answer_key",
        )
        .values(valid_for_summary=False)
        .execution_options(synchronize_session=False)
    )
    setting = session.get(Setting, "suspended_constructions")
    setting.value = {
        "ids": sorted(set(setting.value.get("ids", [])) | {construction_id})
    }
    session.add(
        Event(
            type="construction_reported",
            client_uuid=key,
            data={
                "construction_id": construction_id,
                "version": VERSION,
                "reason": body.reason,
            },
        )
    )
    session.commit()
    return {"suspended": True}


class RestoreConstruction(Request):
    version: str = Field(max_length=80)
    reviewed: Literal[True]


@router.post("/constructions/{construction_id}/restore")
def restore_construction(
    construction_id: str,
    body: RestoreConstruction,
    session: Session = Depends(get_session),
):
    if construction_id not in CONSTRUCTIONS:
        raise HTTPException(404)
    if body.version != VERSION:
        raise HTTPException(409, "Exercise version changed. Reload first")
    from sqlalchemy.dialects.sqlite import insert

    session.execute(
        insert(Setting)
        .values(key="suspended_constructions", value={"ids": []})
        .on_conflict_do_nothing()
    )
    key = f"construction-restore:{construction_id}:{body.request_uuid}"
    if session.scalar(select(Event.id).where(Event.client_uuid == key)):
        return {"suspended": False}
    setting = session.get(Setting, "suspended_constructions")
    setting.value = {
        "ids": [key for key in setting.value.get("ids", []) if key != construction_id]
    }
    session.add(
        Event(
            type="construction_restored",
            client_uuid=key,
            data={
                "construction_id": construction_id,
                "version": VERSION,
                "reviewed": True,
            },
        )
    )
    session.commit()
    return {"suspended": False}
