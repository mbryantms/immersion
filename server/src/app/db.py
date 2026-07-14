"""SQLite engine + session. WAL keeps the API and the single worker from
blocking each other; busy_timeout covers the rare overlap."""

from __future__ import annotations

from sqlalchemy import create_engine, event
from sqlalchemy.orm import Session, sessionmaker

from .config import settings


def make_engine(db_path=None):
    path = db_path or settings.db_path
    path.parent.mkdir(parents=True, exist_ok=True)
    engine = create_engine(f"sqlite:///{path}", connect_args={"timeout": 5})

    @event.listens_for(engine, "connect")
    def _pragmas(dbapi_conn, _record):
        cur = dbapi_conn.cursor()
        cur.execute("PRAGMA journal_mode=WAL")
        cur.execute("PRAGMA synchronous=NORMAL")
        cur.execute("PRAGMA foreign_keys=ON")
        cur.close()

    return engine


engine = None
SessionLocal: sessionmaker[Session] | None = None


def init_engine(db_path=None):
    global engine, SessionLocal
    if engine is None:
        engine = make_engine(db_path)
        SessionLocal = sessionmaker(engine, expire_on_commit=False)
    return engine


def get_session():
    """FastAPI dependency."""
    init_engine()
    with SessionLocal() as session:
        yield session


def upgrade_db():
    """Run Alembic migrations to head (API and worker both call this at boot;
    WAL + busy_timeout serialize the rare race)."""
    from pathlib import Path

    from alembic import command
    from alembic.config import Config

    here = Path(__file__).resolve()
    cfg = Config(str(here.parents[2] / "alembic.ini"))
    cfg.set_main_option("script_location", str(here.parent / "migrations"))
    command.upgrade(cfg, "head")
