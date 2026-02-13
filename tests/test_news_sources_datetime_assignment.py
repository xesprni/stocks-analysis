import asyncio
import tempfile
import unittest
from datetime import datetime
from pathlib import Path

from sqlmodel import Session, select

from market_reporter.api.news_sources import create_news_source, update_news_source
from market_reporter.config import AppConfig, DatabaseConfig
from market_reporter.infra.db.models import NewsSourceTable
from market_reporter.infra.db.session import get_engine, init_db
from market_reporter.modules.news.schemas import (
    NewsSourceCreateRequest,
    NewsSourceUpdateRequest,
)


class NewsSourcesDatetimeAssignmentTest(unittest.TestCase):
    def test_create_and_update_use_datetime_instances(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            db_path = root / "market_reporter.db"
            db_url = f"sqlite:///{db_path}"
            config = AppConfig(
                output_root=root / "output",
                config_file=root / "config" / "settings.yaml",
                database=DatabaseConfig(url=db_url),
            )
            init_db(db_url)

            created = asyncio.run(
                create_news_source(
                    payload=NewsSourceCreateRequest(
                        name="Reuters",
                        category="finance",
                        url="https://www.reuters.com/markets/",
                        enabled=True,
                    ),
                    config=config,
                )
            )
            asyncio.run(
                update_news_source(
                    source_id=created.source_id,
                    payload=NewsSourceUpdateRequest(enabled=False),
                    config=config,
                )
            )

            engine = get_engine(db_url)
            with Session(engine) as session:
                row = session.exec(
                    select(NewsSourceTable).where(
                        NewsSourceTable.source_id == created.source_id
                    )
                ).first()

            self.assertIsNotNone(row)
            assert row is not None
            self.assertIsInstance(row.created_at, datetime)
            self.assertIsInstance(row.updated_at, datetime)
            self.assertFalse(row.enabled)


if __name__ == "__main__":
    unittest.main()
