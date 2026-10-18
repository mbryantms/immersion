"""Synthetic local SQL/API-handler timings; never opens personal data or Anki."""

import argparse
import json
import platform
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
import statistics
from tempfile import TemporaryDirectory
from time import perf_counter

from sqlalchemy import insert
from sqlalchemy.orm import Session

from app.api.exports import inbox, exports
from app.db import make_engine
from app.models import AnkiLink, Base, ExportAttempt, Job, ReviewState, SavedItem


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--cards", type=int, default=10000)
    parser.add_argument("--runs", type=int, default=20)
    args = parser.parse_args()
    if not 100 <= args.cards <= 100000 or not 5 <= args.runs <= 100:
        parser.error("Use 100–100000 cards and 5–100 runs")
    now = datetime.now(timezone.utc)
    with TemporaryDirectory(prefix="immersion-handoff-bench-") as directory:
        engine = make_engine(Path(directory) / "synthetic.db")
        Base.metadata.create_all(engine)
        linked = args.cards // 5
        with Session(engine) as session:
            session.execute(
                insert(SavedItem),
                [
                    {
                        "id": i,
                        "kind": "sentence",
                        "surface": "学习，再学习。",
                        "export_deferred": i % 10 == 0,
                    }
                    for i in range(1, args.cards + 1)
                ],
            )
            session.execute(
                insert(ReviewState),
                [
                    {"saved_item_id": i, "graduated": True, "rung": 2}
                    for i in range(1, args.cards + 1)
                ],
            )
            session.execute(
                insert(Job),
                [
                    {"id": i, "type": "anki_export", "status": "done", "payload": {}}
                    for i in range(1, linked + 1)
                ],
            )
            snap = {
                "fields": {
                    "Simplified": "学习",
                    "Meaning": "to study",
                    "Sentence": "学习，再学习。",
                },
                "profile": {
                    "model": "Synthetic",
                    "deck": "Synthetic",
                    "fields": {"Simplified": "Front", "Meaning": "Back"},
                },
            }
            session.execute(
                insert(ExportAttempt),
                [
                    {
                        "job_id": i,
                        "saved_item_id": i,
                        "original_saved_item_id": i,
                        "export_key": f"synthetic-{i}",
                        "snapshot": snap,
                        "status": "added",
                        "created_at": now,
                        "updated_at": now,
                    }
                    for i in range(1, linked + 1)
                ],
            )
            session.execute(
                insert(AnkiLink),
                [
                    {
                        "saved_item_id": i,
                        "note_id": i + 1000,
                        "deck": "Synthetic",
                        "model": "Synthetic",
                    }
                    for i in range(1, linked + 1)
                ],
            )
            session.commit()
        timings = {}
        for name, call in {
            "inbox_30": lambda session: inbox(
                view="ready", before_id=None, limit=30, session=session
            ),
            "history_20": lambda session: exports(
                before_job_id=None, include_attempt_id=None, session=session
            ),
        }.items():
            values = []
            for _ in range(args.runs + 1):
                with Session(engine) as session:
                    start = perf_counter()
                    call(session)
                    values.append((perf_counter() - start) * 1000)
            values = sorted(values[1:])
            timings[name] = {
                "p50_ms": round(statistics.median(values), 2),
                "p95_ms": round(values[int(0.95 * (len(values) - 1))], 2),
            }
        print(
            json.dumps(
                {
                    "platform": platform.system() + " " + platform.machine(),
                    "python": platform.python_version(),
                    "sqlite": sqlite3.sqlite_version,
                    "cards": args.cards,
                    "linked": linked,
                    "runs": args.runs,
                    "timings": timings,
                },
                indent=2,
            )
        )
        engine.dispose()


if __name__ == "__main__":
    main()
