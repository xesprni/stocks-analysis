"""watchlist symbol+market unique

Revision ID: 20260207_01
Revises: 20260206_03
Create Date: 2026-02-07 18:10:00
"""

from alembic import op


revision = "20260207_01"
down_revision = "20260206_03"
branch_labels = None
depends_on = None


_INDEX_NAME = "uq_watchlist_symbol_market"


def upgrade() -> None:
    # Keep the oldest row when historical duplicates already exist.
    op.execute(
        """
        DELETE FROM watchlist_items
        WHERE id NOT IN (
            SELECT keep_id
            FROM (
                SELECT MIN(id) AS keep_id
                FROM watchlist_items
                GROUP BY symbol, market
            ) AS dedup
        )
        """
    )
    op.create_index(
        _INDEX_NAME,
        "watchlist_items",
        ["symbol", "market"],
        unique=True,
    )


def downgrade() -> None:
    op.drop_index(_INDEX_NAME, table_name="watchlist_items")
