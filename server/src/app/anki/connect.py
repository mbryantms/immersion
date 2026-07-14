"""Minimal AnkiConnect client (Anki desktop must be open)."""

from __future__ import annotations

import httpx

from ..config import settings


class AnkiError(RuntimeError):
    pass


def ac(action: str, **params):
    try:
        r = httpx.post(
            settings.anki_url, json={"action": action, "version": 6, "params": params}, timeout=60
        )
        r.raise_for_status()
    except httpx.HTTPError as e:
        raise AnkiError(f"AnkiConnect unreachable ({e}); is Anki desktop running?") from e
    body = r.json()
    if body.get("error"):
        raise AnkiError(body["error"])
    return body["result"]
