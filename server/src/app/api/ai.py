"""Optional AI policy, exact-request cancellation and immutable artifact feedback."""

from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import select
from sqlalchemy.dialects.sqlite import insert
from sqlalchemy.orm import Session

from ..ai import provider
from ..ai.tasks import explanation_context, generation_state, retry_key
from ..db import get_session
from ..models import AiArtifact, Event, Sentence, Setting

router = APIRouter()


class Policy(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)
    enabled: bool = True
    prefetch: bool = False


def policy(session):
    row = session.get(Setting, "ai-policy")
    return Policy.model_validate(row.value if row else {}).model_dump()


@router.get("/ai-policy")
def get_policy(session: Session = Depends(get_session)):
    return {**policy(session), "provider_available": provider.available()}


@router.put("/ai-policy")
def set_policy(body: Policy, session: Session = Depends(get_session)):
    session.execute(
        insert(Setting)
        .values(key="ai-policy", value=body.model_dump())
        .on_conflict_do_update(index_elements=[Setting.key], set_={"value": body.model_dump()})
    )
    session.commit()
    if not body.enabled:
        provider.cancel_all()
    elif not body.prefetch:
        provider.cancel_prefetches()
    return get_policy(session)


@router.delete("/ai-requests/{request_id}")
def cancel(request_id: UUID):
    return {"cancelled": provider.cancel_request(str(request_id))}


def artifact_for(session, artifact_id):
    artifact = session.get(AiArtifact, artifact_id)
    if not artifact or artifact.artifact_type not in {"explanation", "explanation_extras"}:
        raise HTTPException(404)
    return artifact


class Feedback(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)
    accepted: bool
    reason: str = Field(default="", max_length=1000)


@router.post("/ai-artifacts/{artifact_id}/feedback")
def feedback(artifact_id: int, body: Feedback, session: Session = Depends(get_session)):
    artifact = artifact_for(session, artifact_id)
    artifact.accepted = body.accepted
    session.add(
        Event(
            type="ai_artifact_feedback",
            sentence_id=artifact.target_id,
            data={"artifact_id": artifact.id, **body.model_dump()},
        )
    )
    session.commit()
    return {"artifact_id": artifact.id, "accepted": artifact.accepted}


class Retry(BaseModel):
    model_config = ConfigDict(extra="forbid")
    request_uuid: UUID
    sentence_id: int


@router.post("/ai-artifacts/{artifact_id}/retry")
def retry(artifact_id: int, body: Retry, session: Session = Depends(get_session)):
    # Obtain the SQLite writer lock before inspecting generation/replay state.
    session.execute(
        insert(Setting).values(key="ai-retry-lock", value=True).on_conflict_do_nothing()
    )
    artifact = artifact_for(session, artifact_id)
    sentence = session.get(Sentence, body.sentence_id)
    if not sentence or explanation_context(sentence) != artifact.output.get("_context_hash"):
        raise HTTPException(409, "Source context changed. Reload this sentence before retrying.")
    if artifact.accepted is not False:
        raise HTTPException(409, "Reject this explanation before requesting another attempt")
    event = session.scalar(select(Event).where(Event.client_uuid == str(body.request_uuid)))
    if event:
        if (
            event.type != "ai_artifact_retry"
            or event.data.get("artifact_id") != artifact_id
            or event.sentence_id != sentence.id
        ):
            raise HTTPException(409, "Request identifier already used for another action")
        return event.data
    context = artifact.output["_context_hash"]
    current = generation_state(session, artifact.artifact_type, context)
    generation = max(current, int(artifact.output.get("_generation", 0)) + 1)
    value = {"generation": generation}
    session.execute(
        insert(Setting)
        .values(key=retry_key(artifact.artifact_type, context), value=value)
        .on_conflict_do_update(index_elements=[Setting.key], set_={"value": value})
    )
    data = {"artifact_id": artifact.id, "generation": generation}
    session.add(
        Event(
            type="ai_artifact_retry",
            sentence_id=sentence.id,
            client_uuid=str(body.request_uuid),
            data=data,
        )
    )
    session.commit()
    return data
