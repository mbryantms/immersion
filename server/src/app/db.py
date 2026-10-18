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
    # Backup only when an existing database needs a schema change. Verify a
    # restore before allowing Alembic to touch personal learning history.
    from alembic.migration import MigrationContext
    from alembic.script import ScriptDirectory
    target = ScriptDirectory.from_config(cfg).get_current_head()
    if settings.db_path.exists():
        with make_engine().connect() as connection:
            current = MigrationContext.configure(connection).get_current_revision()
        if current != target:
            from datetime import datetime, timezone
            stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%f")
            verified_backup(settings.db_path, settings.data_dir / "backups" / f"pre-{target}-{stamp}.db")
    command.upgrade(cfg, "head")


def verified_backup(path, destination):
    """Online SQLite backup, then restore into memory and verify integrity.

    SQLite's backup API includes committed WAL content. Never copy the raw DB.
    """
    import sqlite3

    destination.parent.mkdir(parents=True, exist_ok=True)
    with sqlite3.connect(path) as source, sqlite3.connect(destination) as backup:
        source.backup(backup)
        with sqlite3.connect(":memory:") as restored:
            backup.backup(restored)
            if restored.execute("PRAGMA integrity_check").fetchone()[0] != "ok":
                raise RuntimeError("Database backup restore verification failed")
            if restored.execute("PRAGMA foreign_key_check").fetchone() is not None:
                raise RuntimeError("Database backup contains foreign-key inconsistencies")
    return destination
