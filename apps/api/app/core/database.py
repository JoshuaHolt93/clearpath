from __future__ import annotations

from collections.abc import Generator

from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

from app.core.config import get_settings


def _engine_kwargs(url: str) -> dict:
    if url.startswith("sqlite"):
        # 30s busy timeout mirrors the Flask hardening pass (commit 8c9f0bf).
        return {"connect_args": {"check_same_thread": False, "timeout": 30}}
    # Verify pooled connections before use so stale Postgres connections are
    # replaced instead of surfacing as request errors.
    return {"pool_pre_ping": True}


settings = get_settings()
engine = create_engine(settings.database_url, future=True, **_engine_kwargs(settings.database_url))

if settings.database_url.startswith("sqlite") and ":memory:" not in settings.database_url:
    from sqlalchemy import event

    @event.listens_for(engine, "connect")
    def _set_sqlite_pragmas(dbapi_connection, connection_record):
        cursor = dbapi_connection.cursor()
        cursor.execute("PRAGMA journal_mode=WAL")
        cursor.execute("PRAGMA synchronous=NORMAL")
        cursor.close()
SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False, expire_on_commit=False, future=True)


def get_db() -> Generator[Session, None, None]:
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
