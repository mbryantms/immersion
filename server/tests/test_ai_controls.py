"""No real CLI, model, microphone or remote service is used by these checks."""

import copy
from concurrent.futures import ThreadPoolExecutor
import sys
import time
from uuid import uuid4

import pytest
from sqlalchemy import select

from app.ai import provider
from app.ai.validation import InvalidExplanation, validate_result, validate_translations
from app.models import AiArtifact, Event, Sentence
from test_api import client, db_session, seeded  # noqa: F401

CORE = {
    "natural": "Hello.",
    "literal": "hello",
    "structure": "A greeting.",
    "words": [{"zh": "你好", "role": "greeting"}],
    "particles": [],
}


def fake_provider(monkeypatch):
    calls = []
    monkeypatch.setattr(provider, "available", lambda: True)

    def complete(prompt, timeout_s=0):
        calls.append(prompt)
        return copy.deepcopy(CORE)

    monkeypatch.setattr(provider, "complete_json", complete)
    return calls


@pytest.mark.parametrize(
    "change",
    [
        lambda value: value.pop("literal"),
        lambda value: value.update(unexpected=True),
        lambda value: value.update(natural=42),
        lambda value: value.update(
            words=[{"zh": "你", "role": "partial token"}, {"zh": "好", "role": "partial"}]
        ),
        lambda value: value.update(words=[{"zh": "您好", "role": "invented"}]),
        lambda value: value.update(words=[]),
        lambda value: value.update(particles=[{"zh": "了", "note": "not in source"}]),
        lambda value: value.update(particles=[{"zh": "你好", "note": "one"}] * 2),
    ],
)
def test_invalid_core_never_passes_structural_or_token_checks(change):
    value = copy.deepcopy(CORE)
    change(value)
    with pytest.raises(InvalidExplanation):
        validate_result("explanation", value, [{"t": "你好"}])


def test_breakdown_requires_order_and_complete_adjacent_tokens():
    value = copy.deepcopy(CORE)
    value["words"] = [
        {"zh": "我学习", "role": "subject and action"},
        {"zh": "中文", "role": "object"},
    ]
    tokens = [{"t": text} for text in ["我", "学习", "中文"]]
    assert validate_result("explanation", value, tokens)["words"] == value["words"]
    for bad in [[{"zh": "我", "role": "omits tokens"}], list(reversed(value["words"]))]:
        value["words"] = bad
        with pytest.raises(InvalidExplanation):
            validate_result("explanation", value, tokens)


@pytest.mark.parametrize("value", [[None], [42], [{"en": "hello"}], [" "], ["a" * 10001], []])
def test_translations_cannot_coerce_invalid_output(value):
    with pytest.raises(InvalidExplanation):
        validate_translations(value, 1)


def test_policy_defaults_cache_offline_and_rejection_retry(client, seeded, db_session, monkeypatch):  # noqa: F811
    calls = fake_provider(monkeypatch)
    endpoint = f"/api/sentences/{seeded['sentence']}/explain"
    assert client.get("/api/ai-policy").json()["prefetch"] is False
    assert client.post(endpoint + "?prefetch=true").status_code == 409
    first = client.post(endpoint).json()
    assert first["artifact_id"] and first["prompt_version"] == "4"
    assert not any(key.startswith("_") for key in first)
    monkeypatch.setattr(provider, "available", lambda: False)
    assert client.post(endpoint).json()["artifact_id"] == first["artifact_id"]
    feedback = f"/api/ai-artifacts/{first['artifact_id']}/feedback"
    assert (
        client.post(feedback, json={"accepted": False, "reason": "Meaning is wrong"}).status_code
        == 200
    )
    rejected = client.post(endpoint)
    assert rejected.status_code == 409
    assert rejected.json()["detail"]["artifact_id"] == first["artifact_id"]
    retry = f"/api/ai-artifacts/{first['artifact_id']}/retry"
    body = {"request_uuid": str(uuid4()), "sentence_id": seeded["sentence"]}
    one = client.post(retry, json=body)
    assert one.status_code == 200
    assert client.post(retry, json=body).json() == one.json()
    # Separate concurrent intents on the same rejected generation do not skip generations.
    body["request_uuid"] = str(uuid4())
    assert client.post(retry, json=body).json()["generation"] == 1
    monkeypatch.setattr(provider, "available", lambda: True)
    new = client.post(endpoint).json()
    assert new["artifact_id"] != first["artifact_id"] and len(calls) == 2
    with db_session() as session:
        assert session.get(AiArtifact, first["artifact_id"]).accepted is False
        assert (
            len(session.scalars(select(Event).where(Event.type == "ai_artifact_retry")).all()) == 2
        )


def test_invalid_provider_output_is_audited_but_not_cached(client, seeded, db_session, monkeypatch):  # noqa: F811
    fake_provider(monkeypatch)
    monkeypatch.setattr(provider, "complete_json", lambda *a, **k: {"natural": "unverified"})
    result = client.post(f"/api/sentences/{seeded['sentence']}/explain")
    assert result.status_code == 422
    with db_session() as session:
        assert session.scalar(select(AiArtifact.id)) is None
        assert session.scalar(select(Event).where(Event.type == "ai_output_rejected")) is not None


def test_changed_source_discards_completed_output(client, seeded, db_session, monkeypatch):  # noqa: F811
    fake_provider(monkeypatch)

    def complete(*args, **kwargs):
        with db_session() as other:
            sentence = other.get(Sentence, seeded["sentence"])
            sentence.en = "A local correction"
            other.commit()
        return copy.deepcopy(CORE)

    monkeypatch.setattr(provider, "complete_json", complete)
    assert client.post(f"/api/sentences/{seeded['sentence']}/explain").status_code == 409
    with db_session() as session:
        assert session.scalar(select(AiArtifact.id)) is None
        assert session.scalar(select(Event).where(Event.type == "ai_output_discarded"))


def test_disable_generation_and_cancel_before_post(client, seeded, monkeypatch):  # noqa: F811
    calls = fake_provider(monkeypatch)
    endpoint = f"/api/sentences/{seeded['sentence']}/explain"
    request_id = str(uuid4())
    assert client.delete(f"/api/ai-requests/{request_id}").status_code == 200
    assert client.post(endpoint + f"?request_id={request_id}").status_code == 409
    assert not calls
    assert (
        client.put("/api/ai-policy", json={"enabled": False, "prefetch": False}).status_code == 200
    )
    assert client.post(endpoint).status_code == 409
    assert (
        client.put(
            "/api/ai-policy", json={"enabled": True, "prefetch": False, "other": 1}
        ).status_code
        == 422
    )
    assert client.delete("/api/ai-requests/not-a-uuid").status_code == 422


def executable(tmp_path, monkeypatch, source):
    script = tmp_path / "fake-claude"
    script.write_text(f"#!{sys.executable}\n" + source)
    script.chmod(0o700)
    monkeypatch.setattr(provider.shutil, "which", lambda name: str(script))
    monkeypatch.setattr(provider.settings, "data_dir", tmp_path)
    return script


def test_provider_cancellation_kills_only_its_process_and_releases_slot(tmp_path, monkeypatch):
    marker = tmp_path / "started"
    script = executable(
        tmp_path,
        monkeypatch,
        f"import time\nfrom pathlib import Path\nPath({str(marker)!r}).touch()\ntime.sleep(20)\n",
    )
    request_id = str(uuid4())

    def run():
        with provider.request_scope(request_id):
            return provider.complete_json("test", timeout_s=10)

    with ThreadPoolExecutor() as pool:
        future = pool.submit(run)
        deadline = time.monotonic() + 3
        while not marker.exists() and time.monotonic() < deadline:
            time.sleep(0.01)
        assert marker.exists()
        assert provider.cancel_request(request_id)
        with pytest.raises(provider.ProviderCancelled):
            future.result(timeout=3)
    script.write_text(f"#!{sys.executable}\nprint('{{\"ok\":true}}')\n")
    assert provider.complete_json("next") == {"ok": True}


@pytest.mark.parametrize(
    "source,exception",
    [
        ("import time\ntime.sleep(10)\n", provider.ProviderTimeout),
        ("import sys\nsys.stdout.write('x'*300000)\n", provider.ProviderFailed),
        ("import sys\nsys.stderr.write('x'*300000)\n", provider.ProviderFailed),
        ("print('not json')\n", provider.ProviderFailed),
        ("import sys\nsys.exit(1)\n", provider.ProviderFailed),
    ],
)
def test_provider_bounds_timeout_output_and_errors(tmp_path, monkeypatch, source, exception):
    executable(tmp_path, monkeypatch, source)
    with pytest.raises(exception):
        provider.complete_json("test", timeout_s=1)


def test_explicit_queue_outranks_background_and_skips_prefetch():
    order = []
    deadline = time.monotonic() + 4

    def waiting(priority):
        with provider.request_scope(priority=priority):
            with provider._local_slot(priority, deadline):
                order.append(priority)

    with ThreadPoolExecutor() as pool:
        with provider._local_slot("background", deadline):
            background = pool.submit(waiting, "background")
            interactive = pool.submit(waiting, "interactive")
            limit = time.monotonic() + 2
            while len(provider._waiters) < 2 and time.monotonic() < limit:
                time.sleep(0.01)
            assert len(provider._waiters) == 2
            with pytest.raises(provider.ProviderBusy):
                with provider._local_slot("prefetch", deadline):
                    pass
        background.result(timeout=3)
        interactive.result(timeout=3)
    assert order == ["interactive", "background"]


def test_worker_process_lock_skips_prefetch_and_releases_cleanly(tmp_path, monkeypatch):
    import subprocess

    marker = tmp_path / "locked"
    executable(tmp_path, monkeypatch, "print('{\"ok\":true}')\n")
    worker = subprocess.Popen(
        [
            sys.executable,
            "-c",
            "import fcntl,sys; from pathlib import Path; "
            f"lock=open({str(tmp_path / 'ai-provider.lock')!r},'a'); "
            "fcntl.flock(lock,fcntl.LOCK_EX); "
            f"Path({str(marker)!r}).touch(); sys.stdin.readline()",
        ],
        stdin=subprocess.PIPE,
    )
    try:
        deadline = time.monotonic() + 3
        while not marker.exists() and time.monotonic() < deadline:
            time.sleep(0.01)
        assert marker.exists()
        with provider.request_scope(priority="prefetch"):
            with pytest.raises(provider.ProviderBusy):
                provider.complete_json("should not run")
    finally:
        worker.communicate(input=b"release\n", timeout=3)
    assert provider.complete_json("after worker") == {"ok": True}


def test_queued_cancellation_releases_waiter_without_running_provider():
    request_id = str(uuid4())
    deadline = time.monotonic() + 4

    def wait():
        with provider.request_scope(request_id):
            with provider._local_slot("interactive", deadline):
                pytest.fail("Cancelled queue work must not start")

    with ThreadPoolExecutor() as pool:
        with provider._local_slot("background", deadline):
            future = pool.submit(wait)
            limit = time.monotonic() + 2
            while not provider._waiters and time.monotonic() < limit:
                time.sleep(0.01)
            assert provider._waiters
            assert provider.cancel_request(request_id)
            with pytest.raises(provider.ProviderCancelled):
                future.result(timeout=2)
            assert not provider._waiters
