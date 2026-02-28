from __future__ import annotations

import secrets
from contextlib import contextmanager
from datetime import datetime
from functools import lru_cache
from typing import Iterator, List

import bcrypt
from sqlmodel import Session, SQLModel, create_engine, select

from market_reporter.config import NewsSource


def hash_password(password: str) -> str:
    return bcrypt.hashpw(password.encode("utf-8"), bcrypt.gensalt()).decode("utf-8")


def verify_password(plain_password: str, hashed_password: str) -> bool:
    return bcrypt.checkpw(
        plain_password.encode("utf-8"), hashed_password.encode("utf-8")
    )


def generate_random_password(length: int = 16) -> str:
    alphabet = "abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789!@#$%^&*"
    return "".join(secrets.choice(alphabet) for _ in range(length))


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
        now = datetime.utcnow()
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
        if "user_id" not in columns:
            connection.exec_driver_sql(
                "ALTER TABLE watchlist_items ADD COLUMN user_id INTEGER REFERENCES users(id)"
            )

        try:
            user_columns = {
                row[1]
                for row in connection.exec_driver_sql(
                    "PRAGMA table_info('users')"
                ).fetchall()
            }
            if "password_hash" not in user_columns:
                connection.exec_driver_sql(
                    "ALTER TABLE users ADD COLUMN password_hash VARCHAR DEFAULT ''"
                )
            if "last_login_at" not in user_columns:
                connection.exec_driver_sql(
                    "ALTER TABLE users ADD COLUMN last_login_at DATETIME"
                )
            if "updated_at" not in user_columns:
                connection.exec_driver_sql(
                    "ALTER TABLE users ADD COLUMN updated_at DATETIME DEFAULT CURRENT_TIMESTAMP"
                )
        except Exception:
            pass

        try:
            run_columns = {
                row[1]
                for row in connection.exec_driver_sql(
                    "PRAGMA table_info('stock_analysis_runs')"
                ).fetchall()
            }
            if "user_id" not in run_columns:
                connection.exec_driver_sql(
                    "ALTER TABLE stock_analysis_runs ADD COLUMN user_id INTEGER REFERENCES users(id)"
                )
        except Exception:
            pass
        if "keywords_json" not in columns:
            connection.exec_driver_sql(
                "ALTER TABLE watchlist_items ADD COLUMN keywords_json TEXT"
            )


def init_default_admin(
    database_url: str,
    default_username: str = "admin",
    default_password: str | None = None,
) -> str | None:
    """Initialize default admin user if no users exist.

    Returns the generated password if a new admin was created, None otherwise.
    """
    from market_reporter.infra.db.models import UserTable

    engine = get_engine(database_url)
    with Session(engine) as session:
        existing = session.exec(select(UserTable).limit(1)).first()
        if existing is not None:
            return None

        password = default_password or generate_random_password(16)
        password_hash = hash_password(password)

        admin = UserTable(
            username=default_username,
            password_hash=password_hash,
            email=None,
            display_name="Administrator",
            is_admin=True,
            is_active=True,
            created_at=datetime.utcnow(),
            updated_at=datetime.utcnow(),
        )
        session.add(admin)
        session.commit()
        return password
