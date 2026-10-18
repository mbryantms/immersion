"""Bounded local CLI adapter. Provider requests are optional and cancellable.

The CLI may contact its configured remote service. Core study and cached
explanations do not require it. This adapter never handles microphone audio.
"""

from __future__ import annotations

from contextlib import contextmanager
from contextvars import ContextVar
import fcntl
import json
import os
import shutil
import signal
import subprocess
import tempfile
import threading
import time
from uuid import uuid4

from ..config import settings


class ProviderUnavailable(RuntimeError):
    pass


class ProviderBusy(RuntimeError):
    pass


class ProviderCancelled(RuntimeError):
    pass


class ProviderTimeout(RuntimeError):
    pass


class ProviderFailed(RuntimeError):
    pass


_request = ContextVar("ai_request", default=None)
_guard = threading.Lock()
_requests: dict[str, tuple[threading.Event, str]] = {}
_cancelled: dict[str, float] = {}
_condition = threading.Condition()
_waiters: list[tuple[int, object]] = []
_active = False


def available() -> bool:
    return shutil.which("claude") is not None


@contextmanager
def request_scope(request_id=None, priority="interactive"):
    request_id = request_id or str(uuid4())
    event = threading.Event()
    with _guard:
        for key, expiry in list(_cancelled.items()):
            if expiry < time.monotonic():
                del _cancelled[key]
        if request_id in _requests:
            raise ProviderBusy("This request is already running")
        if len(_requests) >= 12:
            raise ProviderBusy("AI request capacity reached; try again shortly")
        if request_id in _cancelled:
            event.set()
        _requests[request_id] = (event, priority)
    token = _request.set((request_id, event, priority))
    try:
        check_cancelled()
        yield
    finally:
        _request.reset(token)
        with _guard:
            _requests.pop(request_id, None)


def cancel_request(request_id):
    with _guard:
        if request_id in _requests:
            _requests[request_id][0].set()
            return True
        # Handles a close/cancel arriving just before the POST reaches the API.
        if len(_cancelled) >= 128:
            _cancelled.pop(next(iter(_cancelled)))
        _cancelled[request_id] = time.monotonic() + 60
        return False


def cancel_prefetches():
    with _guard:
        for event, priority in _requests.values():
            if priority == "prefetch":
                event.set()


def cancel_all():
    with _guard:
        for event, _ in _requests.values():
            event.set()


def check_cancelled():
    context = _request.get()
    if context and context[1].is_set():
        raise ProviderCancelled("AI request cancelled")


@contextmanager
def _local_slot(priority, deadline):
    global _active
    ticket = (
        0 if priority == "interactive" else 1 if priority == "background" else 2,
        object(),
    )
    with _condition:
        if len(_waiters) >= 6 or (priority == "prefetch" and (_active or _waiters)):
            raise ProviderBusy("AI is busy; speculative work skipped")
        _waiters.append(ticket)
        try:
            while _active or min(_waiters, key=lambda value: value[0]) != ticket:
                check_cancelled()
                if time.monotonic() >= deadline:
                    raise ProviderBusy("AI queue is busy; try again shortly")
                _condition.wait(timeout=0.1)
            check_cancelled()
            _active = True
        finally:
            _waiters.remove(ticket)
            _condition.notify_all()
    try:
        yield
    finally:
        with _condition:
            _active = False
            _condition.notify_all()


@contextmanager
def _generation_slot():
    context = _request.get()
    priority = context[2] if context else "background"
    deadline = time.monotonic() + 30
    settings.data_dir.mkdir(parents=True, exist_ok=True)
    # API and worker processes share a file lock. The in-process priority gate
    # favors waiting explicit requests; it cannot preempt an already running job.
    with (settings.data_dir / "ai-provider.lock").open("a") as lock:
        while True:
            check_cancelled()
            if time.monotonic() >= deadline:
                raise ProviderBusy("AI queue is busy; try again shortly")
            with _local_slot(priority, deadline):
                try:
                    fcntl.flock(lock.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
                except BlockingIOError:
                    if priority == "prefetch":
                        raise ProviderBusy("AI is busy; speculative work skipped")
                else:
                    try:
                        yield
                    finally:
                        fcntl.flock(lock.fileno(), fcntl.LOCK_UN)
                    return
            time.sleep(0.05)


def _kill(proc):
    try:
        os.killpg(proc.pid, signal.SIGKILL)
    except ProcessLookupError:
        pass
    try:
        proc.wait(timeout=2)
    except subprocess.TimeoutExpired:
        proc.kill()
        proc.wait(timeout=2)


def complete_json(prompt: str, timeout_s: int = 600) -> list | dict:
    executable = shutil.which("claude")
    if executable is None:
        raise ProviderUnavailable("Optional AI provider is unavailable")
    check_cancelled()
    with (
        _generation_slot(),
        tempfile.TemporaryFile() as output,
        tempfile.TemporaryFile() as errors,
    ):
        # Use a temporary input file as well: writing a large stdin pipe must not
        # block cancellation while a provider starts. No prompt/audio is logged.
        with tempfile.TemporaryFile() as source:
            source.write(prompt.encode())
            source.seek(0)
            try:
                proc = subprocess.Popen(
                    [
                        executable,
                        "-p",
                        "--output-format",
                        "text",
                        "--model",
                        settings.ai_model,
                    ],
                    stdin=source,
                    stdout=output,
                    stderr=errors,
                    start_new_session=True,
                )
            except OSError as error:
                raise ProviderFailed("Optional AI provider could not start") from error
            deadline = time.monotonic() + max(1, min(timeout_s, 600))
            try:
                while proc.poll() is None:
                    check_cancelled()
                    if time.monotonic() >= deadline:
                        raise ProviderTimeout("AI generation timed out")
                    if output.tell() > 256000 or errors.tell() > 256000:
                        raise ProviderFailed("AI response exceeded the size limit")
                    time.sleep(0.05)
                check_cancelled()
            except BaseException:
                if proc.poll() is None:
                    _kill(proc)
                raise
        if proc.returncode != 0:
            raise ProviderFailed("Optional AI provider failed; check its configuration")
        output.seek(0, 2)
        if output.tell() > 256000 or errors.tell() > 256000:
            raise ProviderFailed("AI response exceeded the size limit")
        output.seek(0)
        try:
            value = output.read().decode("utf-8").strip()
        except UnicodeDecodeError as error:
            raise ProviderFailed("AI returned invalid text") from error
    if value.startswith("```") and "\n" in value:
        value = value.split("\n", 1)[1].rsplit("```", 1)[0].strip()
    # Permit a surrounding explanation but parse exactly one JSON value.
    start = min(
        (index for index in (value.find("["), value.find("{")) if index >= 0),
        default=-1,
    )
    if start < 0:
        raise ProviderFailed("AI returned no JSON response")
    try:
        parsed, _ = json.JSONDecoder().raw_decode(value[start:])
    except (ValueError, TypeError) as error:
        raise ProviderFailed("AI returned invalid JSON") from error
    if not isinstance(parsed, (list, dict)):
        raise ProviderFailed("AI response must be an object or array")
    return parsed
