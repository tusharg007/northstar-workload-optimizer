"""Engine and explicit session/transaction ownership."""

from __future__ import annotations

import os
from contextlib import contextmanager
from pathlib import Path
from typing import Iterator

from sqlalchemy import Engine, create_engine, event
from sqlalchemy.engine import make_url
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from app.db.base import Base

DEFAULT_DATABASE_URL = "sqlite:///data/northstar_runtime.db"


def normalize_database_url(value: str | Path | None = None) -> str:
    """Resolve an explicit URL/path or the safe local environment default."""
    if isinstance(value, Path):
        return f"sqlite:///{value.resolve().as_posix()}"
    if value is not None:
        text = str(value)
        if "://" not in text:
            return f"sqlite:///{Path(text).resolve().as_posix()}"
        return text
    return os.getenv("NORTHSTAR_DATABASE_URL", DEFAULT_DATABASE_URL)


def _ensure_sqlite_parent(database_url: str) -> None:
    url = make_url(database_url)
    if url.get_backend_name() != "sqlite" or not url.database:
        return
    if url.database == ":memory:":
        return
    Path(url.database).expanduser().resolve().parent.mkdir(parents=True, exist_ok=True)


def create_database_engine(database_url: str) -> Engine:
    """Create a synchronous engine with SQLite compatibility safeguards."""
    _ensure_sqlite_parent(database_url)
    url = make_url(database_url)
    options: dict = {"pool_pre_ping": True}
    if url.get_backend_name() == "sqlite":
        options["connect_args"] = {"check_same_thread": False, "timeout": 5}
        if url.database == ":memory:":
            options["poolclass"] = StaticPool
    engine = create_engine(database_url, **options)

    if url.get_backend_name() == "sqlite":
        @event.listens_for(engine, "connect")
        def _enable_foreign_keys(dbapi_connection, connection_record) -> None:
            cursor = dbapi_connection.cursor()
            cursor.execute("PRAGMA foreign_keys=ON")
            cursor.close()

    return engine


class Database:
    """Own the engine and short-lived synchronous SQLAlchemy sessions."""

    def __init__(
        self,
        database_url: str | Path | None = None,
        *,
        create_schema: bool = False,
    ) -> None:
        self.url = normalize_database_url(database_url)
        self.engine = create_database_engine(self.url)
        self.session_factory = sessionmaker(
            bind=self.engine,
            class_=Session,
            expire_on_commit=False,
        )
        if create_schema:
            self.create_schema()

    def create_schema(self) -> None:
        """Create schema for disposable tests and the SQLite fallback."""
        from app.db import models  # noqa: F401 - register mappings

        Base.metadata.create_all(self.engine)

    @contextmanager
    def transaction(self) -> Iterator[Session]:
        """Yield one atomic transaction, rolling back on any exception."""
        with self.session_factory() as session:
            with session.begin():
                yield session

    @contextmanager
    def session(self) -> Iterator[Session]:
        """Yield a read-oriented session."""
        with self.session_factory() as session:
            yield session

    def dispose(self) -> None:
        self.engine.dispose()
