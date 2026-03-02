from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from market_reporter.infra.db.repos import (
    AnalysisProviderAccountRepo,
    AnalysisProviderSecretRepo,
    UserRepo,
)
from market_reporter.infra.db.session import (
    get_engine,
    hash_password,
    init_db,
    session_scope,
)


class SqliteProviderCredentialIndexMigrationTest(unittest.TestCase):
    def test_init_db_replaces_legacy_provider_unique_indexes(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = Path(tmpdir) / "legacy.db"
            db_url = f"sqlite:///{db_path}"
            self._create_legacy_provider_tables(db_url)

            init_db(db_url)

            secret_indexes = self._unique_index_columns(
                db_url, "analysis_provider_secrets"
            )
            account_indexes = self._unique_index_columns(
                db_url, "analysis_provider_accounts"
            )
            self.assertIn(("user_id", "provider_id"), secret_indexes)
            self.assertIn(("user_id", "provider_id"), account_indexes)
            self.assertNotIn(("provider_id",), secret_indexes)
            self.assertNotIn(("provider_id",), account_indexes)

            with session_scope(db_url) as session:
                user_repo = UserRepo(session)
                user1 = user_repo.create(
                    username="migration-u1",
                    password_hash=hash_password("pw-u1"),
                )
                user2 = user_repo.create(
                    username="migration-u2",
                    password_hash=hash_password("pw-u2"),
                )
                user1_id = int(user1.id or 0)
                user2_id = int(user2.id or 0)

            with session_scope(db_url) as session:
                AnalysisProviderSecretRepo(session).upsert(
                    provider_id="glm_coding_plan",
                    ciphertext="cipher-u1",
                    nonce="nonce-u1",
                    user_id=user1_id,
                )
                AnalysisProviderSecretRepo(session).upsert(
                    provider_id="glm_coding_plan",
                    ciphertext="cipher-u2",
                    nonce="nonce-u2",
                    user_id=user2_id,
                )
                AnalysisProviderAccountRepo(session).upsert(
                    provider_id="codex_app_server",
                    account_type="chatgpt",
                    credential_ciphertext="credential-u1",
                    nonce="nonce-u1",
                    expires_at=None,
                    user_id=user1_id,
                )
                AnalysisProviderAccountRepo(session).upsert(
                    provider_id="codex_app_server",
                    account_type="chatgpt",
                    credential_ciphertext="credential-u2",
                    nonce="nonce-u2",
                    expires_at=None,
                    user_id=user2_id,
                )

            engine = get_engine(db_url)
            with engine.begin() as connection:
                secret_count = int(
                    connection.exec_driver_sql(
                        "SELECT COUNT(*) FROM analysis_provider_secrets WHERE provider_id = ?",
                        ("glm_coding_plan",),
                    ).scalar_one()
                )
                account_count = int(
                    connection.exec_driver_sql(
                        "SELECT COUNT(*) FROM analysis_provider_accounts WHERE provider_id = ?",
                        ("codex_app_server",),
                    ).scalar_one()
                )
            self.assertEqual(secret_count, 3)
            self.assertEqual(account_count, 3)

    def _create_legacy_provider_tables(self, db_url: str) -> None:
        engine = get_engine(db_url)
        with engine.begin() as connection:
            connection.exec_driver_sql(
                """
                CREATE TABLE analysis_provider_secrets (
                    id INTEGER PRIMARY KEY,
                    provider_id VARCHAR NOT NULL,
                    key_ciphertext VARCHAR NOT NULL,
                    nonce VARCHAR NOT NULL,
                    created_at DATETIME NOT NULL,
                    updated_at DATETIME NOT NULL
                )
                """
            )
            connection.exec_driver_sql(
                "CREATE UNIQUE INDEX ix_analysis_provider_secrets_provider_id ON analysis_provider_secrets (provider_id)"
            )
            connection.exec_driver_sql(
                """
                INSERT INTO analysis_provider_secrets (
                    provider_id,
                    key_ciphertext,
                    nonce,
                    created_at,
                    updated_at
                ) VALUES (?, ?, ?, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)
                """,
                ("glm_coding_plan", "cipher-global", "nonce-global"),
            )

            connection.exec_driver_sql(
                """
                CREATE TABLE analysis_provider_accounts (
                    id INTEGER PRIMARY KEY,
                    provider_id VARCHAR NOT NULL,
                    account_type VARCHAR NOT NULL,
                    credential_ciphertext VARCHAR NOT NULL,
                    nonce VARCHAR NOT NULL,
                    expires_at DATETIME,
                    created_at DATETIME NOT NULL,
                    updated_at DATETIME NOT NULL
                )
                """
            )
            connection.exec_driver_sql(
                "CREATE UNIQUE INDEX ix_analysis_provider_accounts_provider_id ON analysis_provider_accounts (provider_id)"
            )
            connection.exec_driver_sql(
                """
                INSERT INTO analysis_provider_accounts (
                    provider_id,
                    account_type,
                    credential_ciphertext,
                    nonce,
                    expires_at,
                    created_at,
                    updated_at
                ) VALUES (?, ?, ?, ?, ?, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)
                """,
                (
                    "codex_app_server",
                    "chatgpt",
                    "credential-global",
                    "nonce-global",
                    None,
                ),
            )

    def _unique_index_columns(
        self, db_url: str, table_name: str
    ) -> set[tuple[str, ...]]:
        engine = get_engine(db_url)
        with engine.begin() as connection:
            index_rows = connection.exec_driver_sql(
                f"PRAGMA index_list('{table_name}')"
            ).fetchall()
            result: set[tuple[str, ...]] = set()
            for row in index_rows:
                if not bool(row[2]):
                    continue
                index_name = str(row[1])
                columns = tuple(
                    item[2]
                    for item in connection.exec_driver_sql(
                        f"PRAGMA index_info('{index_name}')"
                    ).fetchall()
                )
                result.add(columns)
            return result


if __name__ == "__main__":
    unittest.main()
