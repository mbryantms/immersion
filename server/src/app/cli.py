"""`immersion` CLI: run services and one-off admin tasks."""

from __future__ import annotations

import argparse


def main() -> None:
    ap = argparse.ArgumentParser(prog="immersion")
    sub = ap.add_subparsers(dest="cmd", required=True)

    sub.add_parser("api", help="run the API server")
    sub.add_parser("worker", help="run the background worker")
    sub.add_parser("upgrade", help="run DB migrations")

    p_root = sub.add_parser("add-root", help="register a media root and queue a scan")
    from .config import validate_root_slug
    p_root.add_argument("slug", type=validate_root_slug)
    p_root.add_argument("path")
    p_root.add_argument("--kind", default="video", choices=["video", "podcast"])
    p_root.add_argument("--include", default=None, help="glob(s), ';'-separated, e.g. 'Level */*'")

    sub.add_parser("scan", help="queue a scan of all roots")
    p_reanalyze = sub.add_parser("reanalyze", help="backfill Mandarin metadata in place; preserves sentence IDs")
    p_reanalyze.add_argument("--item-id", type=int, default=None, help="one item; otherwise queue all items")

    args = ap.parse_args()

    if args.cmd == "api":
        import uvicorn

        from .config import settings

        uvicorn.run("app.main:app", host=settings.host, port=settings.port)
        return

    if args.cmd == "worker":
        from .worker import main as worker_main

        worker_main()
        return

    from . import db

    db.init_engine()
    db.upgrade_db()
    if args.cmd == "upgrade":
        print("migrated to head")
        return

    from .jobs import enqueue
    from .models import MediaRoot

    with db.SessionLocal() as session:
        if args.cmd == "add-root":
            root = MediaRoot(slug=args.slug, kind=args.kind, path=args.path,
                             include_glob=args.include)
            session.add(root)
            session.commit()
            enqueue(session, "scan_root", {"root_id": root.id})
            print(f"root {args.slug} -> #{root.id}, scan queued")
        elif args.cmd == "reanalyze":
            if args.item_id is not None:
                enqueue(session, "reanalyze_item", {"item_id": args.item_id}, priority=-1)
                print(f"queued in-place analysis for item {args.item_id}")
            else:
                enqueue(session, "reanalyze_all", None, priority=-1)
                print("queued in-place analysis backfill; run the worker to process items")
        elif args.cmd == "scan":
            enqueue(session, "scan_all", None)
            print("scan queued")


if __name__ == "__main__":
    main()
