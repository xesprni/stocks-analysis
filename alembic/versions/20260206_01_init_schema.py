"""init schema

Revision ID: 20260206_01
Revises: 
Create Date: 2026-02-06 00:00:00
"""

from alembic import op
import sqlalchemy as sa


revision = "20260206_01"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "watchlist_items",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("symbol", sa.String(), nullable=False),
        sa.Column("market", sa.String(), nullable=False),
        sa.Column("alias", sa.String(), nullable=True),
        sa.Column("enabled", sa.Boolean(), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_watchlist_items_symbol", "watchlist_items", ["symbol"], unique=False)
    op.create_index("ix_watchlist_items_market", "watchlist_items", ["market"], unique=False)
    op.create_index("ix_watchlist_items_enabled", "watchlist_items", ["enabled"], unique=False)

    op.create_table(
        "stock_kline_bars",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("symbol", sa.String(), nullable=False),
        sa.Column("market", sa.String(), nullable=False),
        sa.Column("interval", sa.String(), nullable=False),
        sa.Column("ts", sa.String(), nullable=False),
        sa.Column("open", sa.Float(), nullable=False),
        sa.Column("high", sa.Float(), nullable=False),
        sa.Column("low", sa.Float(), nullable=False),
        sa.Column("close", sa.Float(), nullable=False),
        sa.Column("volume", sa.Float(), nullable=True),
        sa.Column("source", sa.String(), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("symbol", "market", "interval", "ts", name="uq_kline_symbol_market_interval_ts"),
    )
    op.create_index("ix_stock_kline_bars_symbol", "stock_kline_bars", ["symbol"], unique=False)
    op.create_index("ix_stock_kline_bars_market", "stock_kline_bars", ["market"], unique=False)
    op.create_index("ix_stock_kline_bars_interval", "stock_kline_bars", ["interval"], unique=False)
    op.create_index("ix_stock_kline_bars_ts", "stock_kline_bars", ["ts"], unique=False)

    op.create_table(
        "stock_curve_points",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("symbol", sa.String(), nullable=False),
        sa.Column("market", sa.String(), nullable=False),
        sa.Column("ts", sa.String(), nullable=False),
        sa.Column("price", sa.Float(), nullable=False),
        sa.Column("volume", sa.Float(), nullable=True),
        sa.Column("source", sa.String(), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_stock_curve_points_symbol", "stock_curve_points", ["symbol"], unique=False)
    op.create_index("ix_stock_curve_points_market", "stock_curve_points", ["market"], unique=False)
    op.create_index("ix_stock_curve_points_ts", "stock_curve_points", ["ts"], unique=False)

    op.create_table(
        "analysis_provider_secrets",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("provider_id", sa.String(), nullable=False),
        sa.Column("key_ciphertext", sa.String(), nullable=False),
        sa.Column("nonce", sa.String(), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_analysis_provider_secrets_provider_id", "analysis_provider_secrets", ["provider_id"], unique=True)

    op.create_table(
        "stock_analysis_runs",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("symbol", sa.String(), nullable=False),
        sa.Column("market", sa.String(), nullable=False),
        sa.Column("provider_id", sa.String(), nullable=False),
        sa.Column("model", sa.String(), nullable=False),
        sa.Column("status", sa.String(), nullable=False),
        sa.Column("input_json", sa.Text(), nullable=False),
        sa.Column("output_json", sa.Text(), nullable=False),
        sa.Column("markdown", sa.Text(), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_stock_analysis_runs_symbol", "stock_analysis_runs", ["symbol"], unique=False)
    op.create_index("ix_stock_analysis_runs_market", "stock_analysis_runs", ["market"], unique=False)
    op.create_index("ix_stock_analysis_runs_provider_id", "stock_analysis_runs", ["provider_id"], unique=False)
    op.create_index("ix_stock_analysis_runs_status", "stock_analysis_runs", ["status"], unique=False)
    op.create_index("ix_stock_analysis_runs_created_at", "stock_analysis_runs", ["created_at"], unique=False)


def downgrade() -> None:
    op.drop_index("ix_stock_analysis_runs_created_at", table_name="stock_analysis_runs")
    op.drop_index("ix_stock_analysis_runs_status", table_name="stock_analysis_runs")
    op.drop_index("ix_stock_analysis_runs_provider_id", table_name="stock_analysis_runs")
    op.drop_index("ix_stock_analysis_runs_market", table_name="stock_analysis_runs")
    op.drop_index("ix_stock_analysis_runs_symbol", table_name="stock_analysis_runs")
    op.drop_table("stock_analysis_runs")

    op.drop_index("ix_analysis_provider_secrets_provider_id", table_name="analysis_provider_secrets")
    op.drop_table("analysis_provider_secrets")

    op.drop_index("ix_stock_curve_points_ts", table_name="stock_curve_points")
    op.drop_index("ix_stock_curve_points_market", table_name="stock_curve_points")
    op.drop_index("ix_stock_curve_points_symbol", table_name="stock_curve_points")
    op.drop_table("stock_curve_points")

    op.drop_index("ix_stock_kline_bars_ts", table_name="stock_kline_bars")
    op.drop_index("ix_stock_kline_bars_interval", table_name="stock_kline_bars")
    op.drop_index("ix_stock_kline_bars_market", table_name="stock_kline_bars")
    op.drop_index("ix_stock_kline_bars_symbol", table_name="stock_kline_bars")
    op.drop_table("stock_kline_bars")

    op.drop_index("ix_watchlist_items_enabled", table_name="watchlist_items")
    op.drop_index("ix_watchlist_items_market", table_name="watchlist_items")
    op.drop_index("ix_watchlist_items_symbol", table_name="watchlist_items")
    op.drop_table("watchlist_items")
