"""AI provider abstraction. Default adapter shells out to the Claude Code CLI
(`claude -p`) — subscription auth, no API key on disk. Ported from podreader's
translate.py. The app is fully functional with AI disabled: sentences simply
keep en=NULL until a provider is available."""

from __future__ import annotations

import json
import shutil
import subprocess

from ..config import settings


class ProviderUnavailable(RuntimeError):
    pass


def available() -> bool:
    return shutil.which("claude") is not None


def complete_json(prompt: str, timeout_s: int = 600) -> list | dict:
    """One CLI completion, parsed as JSON (tolerates ```json fences and prose
    around the payload — takes the outermost [...] or {...})."""
    if not available():
        raise ProviderUnavailable("claude CLI not on PATH")
    proc = subprocess.run(
        ["claude", "-p", "--output-format", "text", "--model", settings.ai_model],
        input=prompt, capture_output=True, text=True, timeout=timeout_s,
    )
    if proc.returncode != 0:
        raise RuntimeError(f"claude -p failed: {proc.stderr[:500]}")
    text = proc.stdout.strip()
    if text.startswith("```"):
        text = text.split("\n", 1)[1].rsplit("```", 1)[0]
    start = min((i for i in (text.find("["), text.find("{")) if i >= 0), default=-1)
    if start < 0:
        raise RuntimeError(f"no JSON in claude output: {text[:200]}")
    end = text.rfind("]") if text[start] == "[" else text.rfind("}")
    return json.loads(text[start : end + 1])
