"""news listener and symbol search schema

Revision ID: 20260206_02
Revises: 20260206_01
Create Date: 2026-02-06 00:30:00
"""

from alembic import op
import sqlalchemy as sa


revision = "20260206_02"
down_revision = "20260206_01"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("watchlist_items", sa.Column("display_name", sa.String(), nullable=True))
    op.add_column("watchlist_items", sa.Column("keywords_json", sa.Text(), nullable=True))

    op.create_table(
        "news_listener_runs",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("started_at", sa.DateTime(), nullable=False),
        sa.Column("finished_at", sa.DateTime(), nullable=False),
        sa.Column("status", sa.String(), nullable=False),
        sa.Column("scanned_news_count", sa.Integer(), nullable=False),
        sa.Column("matched_news_count", sa.Integer(), nullable=False),
        sa.Column("alerts_count", sa.Integer(), nullable=False),
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_news_listener_runs_started_at", "news_listener_runs", ["started_at"], unique=False)
    op.create_index("ix_news_listener_runs_status", "news_listener_runs", ["status"], unique=False)

    op.create_table(
        "watchlist_news_alerts",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("run_id", sa.Integer(), nullable=False),
        sa.Column("symbol", sa.String(), nullable=False),
        sa.Column("market", sa.String(), nullable=False),
        sa.Column("news_title", sa.Text(), nullable=False),
        sa.Column("news_link", sa.Text(), nullable=True),
        sa.Column("news_source", sa.String(), nullable=True),
        sa.Column("published_at", sa.String(), nullable=True),
        sa.Column("move_window_minutes", sa.Integer(), nullable=False),
        sa.Column("price_change_percent", sa.Float(), nullable=False),
        sa.Column("threshold_percent", sa.Float(), nullable=False),
        sa.Column("severity", sa.String(), nullable=False),
        sa.Column("analysis_summary", sa.Text(), nullable=False),
        sa.Column("analysis_markdown", sa.Text(), nullable=False),
        sa.Column("analysis_json", sa.Text(), nullable=False),
        sa.Column("status", sa.String(), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(["run_id"], ["news_listener_runs.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_watchlist_news_alerts_run_id", "watchlist_news_alerts", ["run_id"], unique=False)
    op.create_index("ix_watchlist_news_alerts_symbol", "watchlist_news_alerts", ["symbol"], unique=False)
    op.create_index("ix_watchlist_news_alerts_market", "watchlist_news_alerts", ["market"], unique=False)
    op.create_index("ix_watchlist_news_alerts_severity", "watchlist_news_alerts", ["severity"], unique=False)
    op.create_index("ix_watchlist_news_alerts_status", "watchlist_news_alerts", ["status"], unique=False)
    op.create_index("ix_watchlist_news_alerts_created_at", "watchlist_news_alerts", ["created_at"], unique=False)
    op.create_index(
        "ix_watchlist_news_alerts_symbol_market_created_at",
        "watchlist_news_alerts",
        ["symbol", "market", "created_at"],
        unique=False,
    )
    op.create_index(
        "ix_watchlist_news_alerts_status_created_at",
        "watchlist_news_alerts",
        ["status", "created_at"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index("ix_watchlist_news_alerts_status_created_at", table_name="watchlist_news_alerts")
    op.drop_index("ix_watchlist_news_alerts_symbol_market_created_at", table_name="watchlist_news_alerts")
    op.drop_index("ix_watchlist_news_alerts_created_at", table_name="watchlist_news_alerts")
    op.drop_index("ix_watchlist_news_alerts_status", table_name="watchlist_news_alerts")
    op.drop_index("ix_watchlist_news_alerts_severity", table_name="watchlist_news_alerts")
    op.drop_index("ix_watchlist_news_alerts_market", table_name="watchlist_news_alerts")
    op.drop_index("ix_watchlist_news_alerts_symbol", table_name="watchlist_news_alerts")
    op.drop_index("ix_watchlist_news_alerts_run_id", table_name="watchlist_news_alerts")
    op.drop_table("watchlist_news_alerts")

    op.drop_index("ix_news_listener_runs_status", table_name="news_listener_runs")
    op.drop_index("ix_news_listener_runs_started_at", table_name="news_listener_runs")
    op.drop_table("news_listener_runs")

    op.drop_column("watchlist_items", "keywords_json")
    op.drop_column("watchlist_items", "display_name")
