"""Minimal AnkiConnect client (Anki desktop must be open)."""

from __future__ import annotations

import httpx

from ..config import settings


class AnkiError(RuntimeError):
    pass


class AnkiUnavailable(AnkiError):
    """Transport/protocol failure; a remote mutation may already have happened."""


def ac(action: str, **params):
    try:
        r = httpx.post(
            settings.anki_url, json={"action": action, "version": 6, "params": params}, timeout=httpx.Timeout(15, connect=2)
        )
        r.raise_for_status()
    except httpx.HTTPError as e:
        raise AnkiUnavailable(
            "AnkiConnect is unreachable; open Anki Desktop with AnkiConnect"
        ) from e
    try:
        body = r.json()
        if not isinstance(body, dict) or "result" not in body or "error" not in body:
            raise ValueError("Invalid response envelope")
    except ValueError as error:
        raise AnkiUnavailable("AnkiConnect returned an invalid response") from error
    if body.get("error"):
        raise AnkiError(body["error"])
    return body["result"]
