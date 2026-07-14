"""Video metadata (ffprobe), series inference, sidecar subtitle discovery."""

from __future__ import annotations

import json
import re
import subprocess
from pathlib import Path, PurePosixPath

VIDEO_EXTS = {".mp4", ".mkv", ".webm", ".m4v"}
SUB_EXTS = {".srt", ".vtt", ".ass", ".ssa"}

# language markers seen between the stem and the subtitle extension (LIB-004)
EN_MARKERS = {"en", "eng", "english"}
ZH_MARKERS = {"zh", "chs", "sc", "chi", "zho", "cmn", "zh-hans", "zh-cn", "zh-sg",
              "simplified", "mandarin", "tc", "cht", "zh-hant", "zh-tw", "traditional"}


def ffprobe(path: Path) -> dict:
    out = subprocess.run(
        ["ffprobe", "-v", "quiet", "-print_format", "json",
         "-show_format", "-show_streams", str(path)],
        capture_output=True, text=True, check=True,
    ).stdout
    return json.loads(out)


def probe_summary(path: Path) -> dict:
    """duration_ms, vcodec, acodec, width, height, embedded subtitle stream list."""
    info = ffprobe(path)
    fmt = info.get("format", {})
    res = {
        "duration_ms": int(float(fmt.get("duration", 0)) * 1000) or None,
        "vcodec": None, "acodec": None, "width": None, "height": None,
        "embedded_subs": [],
    }
    for s in info.get("streams", []):
        kind = s.get("codec_type")
        if kind == "video" and res["vcodec"] is None:
            res.update(vcodec=s.get("codec_name"), width=s.get("width"), height=s.get("height"))
        elif kind == "audio" and res["acodec"] is None:
            res["acodec"] = s.get("codec_name")
        elif kind == "subtitle":
            res["embedded_subs"].append({
                "index": s.get("index"),
                "codec": s.get("codec_name"),
                "lang": (s.get("tags") or {}).get("language"),
            })
    return res


SXXEXX = re.compile(r"[Ss](\d{1,2})[Ee](\d{1,3})")


def natural_key(name: str) -> tuple:
    """Numeric-aware sort key: 'Kip 2' < 'Kip 10'."""
    return tuple(int(p) if p.isdigit() else p.casefold() for p in re.split(r"(\d+)", name))


def episode_position(base: Path, relpath: str) -> int | None:
    """Viewing-order ordinal for LFC layouts: the episode directory's position
    among its natural-sorted siblings. This is the on-disk order — it respects
    explicit prefixes ('001 Space Patrol …'), keeps multi-arc series contiguous
    ('Rocket Girl vs. Bubbles 1..12' doesn't interleave with other arcs), and
    numbers unnumbered one-off stories. Number-in-stem inference can't do any
    of that: arcs reuse 1..N and one-offs have nothing to match."""
    parts = PurePosixPath(relpath).parts
    if len(parts) < 4 or not re.fullmatch(r"[Ll]evel \d+", parts[0]):
        return None
    series_dir = base / parts[0] / parts[1]
    try:
        siblings = sorted((d.name for d in series_dir.iterdir() if d.is_dir()), key=natural_key)
    except OSError:
        return None
    try:
        return siblings.index(parts[2]) + 1  # 1-based: shown as "Episode N"
    except ValueError:
        return None


def infer_series(relpath: str) -> tuple[str | None, int | None, int | None]:
    """(series_title, level_hint, ordinal) from a root-relative path.

    LFC layout: 'Level N/<Series>/<Episode Name>/<Episode Name>.mp4' where the
    episode name is '<Series> <num> <title words>'. Generic fallbacks: SxxExx,
    then parent-dir-as-series with the first integer in the stem as ordinal."""
    parts = PurePosixPath(relpath).parts
    stem = PurePosixPath(relpath).stem
    level = None
    m = re.fullmatch(r"[Ll]evel (\d+)", parts[0]) if len(parts) > 1 else None
    if m:
        level = int(m.group(1))
    # LFC: Level N/Series/Episode dir/file
    if level is not None and len(parts) >= 3:
        series = parts[1]
        rest = stem[len(series):] if stem.startswith(series) else stem
        num = re.search(r"\d+", rest)
        return series, level, int(num.group()) if num else None
    m = SXXEXX.search(stem)
    if m and len(parts) >= 2:
        return parts[0], None, int(m.group(1)) * 100 + int(m.group(2))
    if len(parts) >= 2:
        num = re.search(r"\d+", stem)
        return parts[-2], None, int(num.group()) if num else None
    return None, None, None


def find_sidecars(path: Path) -> list[dict]:
    """Subtitle files next to a video sharing its stem.

    Returns [{path, lang: 'zh'|'en'|None, marker}] — lang None means 'sniff the
    content' (bare .srt)."""
    out = []
    stem = path.stem
    for f in sorted(path.parent.iterdir()):
        if f.suffix.lower() not in SUB_EXTS or not f.name.startswith(stem):
            continue
        middle = f.name[len(stem):-len(f.suffix)].strip(". -_").lower()
        if middle in EN_MARKERS:
            lang = "en"
        elif middle in ZH_MARKERS or middle == "":
            lang = "zh" if middle else None
        else:
            continue  # unrelated file that happens to share the prefix
        out.append({"path": f, "lang": lang, "marker": middle})
    return out
