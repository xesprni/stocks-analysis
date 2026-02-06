from __future__ import annotations

from contextlib import contextmanager
from functools import lru_cache
from typing import Iterator

from sqlmodel import Session, SQLModel, create_engine


@lru_cache(maxsize=8)
def get_engine(database_url: str):
    connect_args = {"check_same_thread": False} if database_url.startswith("sqlite") else {}
    return create_engine(database_url, echo=False, connect_args=connect_args)


def init_db(database_url: str) -> None:
    from market_reporter.infra.db import models  # noqa: F401

    engine = get_engine(database_url)
    SQLModel.metadata.create_all(engine)
    if database_url.startswith("sqlite"):
        _ensure_sqlite_columns(engine)


@contextmanager
def session_scope(database_url: str) -> Iterator[Session]:
    engine = get_engine(database_url)
    session = Session(engine)
    try:
        yield session
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()


def _ensure_sqlite_columns(engine) -> None:
    with engine.begin() as connection:
        columns = {
            row[1]
            for row in connection.exec_driver_sql("PRAGMA table_info('watchlist_items')").fetchall()
        }
        if "display_name" not in columns:
            connection.exec_driver_sql("ALTER TABLE watchlist_items ADD COLUMN display_name VARCHAR")
        if "keywords_json" not in columns:
            connection.exec_driver_sql("ALTER TABLE watchlist_items ADD COLUMN keywords_json TEXT")
