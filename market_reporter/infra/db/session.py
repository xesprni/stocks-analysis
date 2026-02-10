from __future__ import annotations

from contextlib import contextmanager
from datetime import datetime
from functools import lru_cache
from typing import Iterator, List

from sqlmodel import Session, SQLModel, create_engine, select

from market_reporter.config import NewsSource


@lru_cache(maxsize=8)
def get_engine(database_url: str):
    # Reuse engine instances per URL so workers do not rebuild connection pools.
    connect_args = (
        {"check_same_thread": False} if database_url.startswith("sqlite") else {}
    )
    return create_engine(database_url, echo=False, connect_args=connect_args)


def init_db(database_url: str) -> None:
    # Import models for side effects so SQLModel metadata includes all tables.
    from market_reporter.infra.db import models  # noqa: F401

    engine = get_engine(database_url)
    SQLModel.metadata.create_all(engine)
    if database_url.startswith("sqlite"):
        # SQLite lacks robust migration tooling in this project; patch missing columns defensively.
        _ensure_sqlite_columns(engine)


def seed_news_sources(database_url: str, sources: List[NewsSource]) -> None:
    """Seed news sources into DB if the table is empty.

    Called on startup to populate defaults or migrate from YAML.
    """
    from market_reporter.infra.db.models import NewsSourceTable

    engine = get_engine(database_url)
    with Session(engine) as session:
        existing = session.exec(select(NewsSourceTable).limit(1)).first()
        if existing is not None:
            return
        now = datetime.utcnow
        for source in sources:
            row = NewsSourceTable(
                source_id=source.source_id or "",
                name=source.name,
                category=source.category,
                url=source.url,
                enabled=source.enabled,
                created_at=now,
                updated_at=now,
            )
            session.add(row)
        session.commit()


@contextmanager
def session_scope(database_url: str) -> Iterator[Session]:
    engine = get_engine(database_url)
    session = Session(engine)
    try:
        yield session
        # Commit once per unit of work; callers can compose multiple repo writes atomically.
        session.commit()
    except Exception:
        # Any failure in the scope rolls back all staged changes.
        session.rollback()
        raise
    finally:
        session.close()


def _ensure_sqlite_columns(engine) -> None:
    with engine.begin() as connection:
        # Lightweight schema compatibility check for local SQLite deployments.
        columns = {
            row[1]
            for row in connection.exec_driver_sql(
                "PRAGMA table_info('watchlist_items')"
            ).fetchall()
        }
        if "display_name" not in columns:
            connection.exec_driver_sql(
                "ALTER TABLE watchlist_items ADD COLUMN display_name VARCHAR"
            )
        if "keywords_json" not in columns:
            connection.exec_driver_sql(
                "ALTER TABLE watchlist_items ADD COLUMN keywords_json TEXT"
            )
