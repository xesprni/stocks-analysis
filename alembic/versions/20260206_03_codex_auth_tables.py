"""codex auth tables

Revision ID: 20260206_03
Revises: 20260206_02
Create Date: 2026-02-06 19:10:00
"""

from alembic import op
import sqlalchemy as sa


revision = "20260206_03"
down_revision = "20260206_02"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "analysis_provider_accounts",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("provider_id", sa.String(), nullable=False),
        sa.Column("account_type", sa.String(), nullable=False),
        sa.Column("credential_ciphertext", sa.Text(), nullable=False),
        sa.Column("nonce", sa.String(), nullable=False),
        sa.Column("expires_at", sa.DateTime(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_analysis_provider_accounts_provider_id",
        "analysis_provider_accounts",
        ["provider_id"],
        unique=True,
    )

    op.create_table(
        "analysis_provider_auth_states",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("state", sa.String(), nullable=False),
        sa.Column("provider_id", sa.String(), nullable=False),
        sa.Column("redirect_to", sa.String(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("expires_at", sa.DateTime(), nullable=False),
        sa.Column("used", sa.Boolean(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_analysis_provider_auth_states_state",
        "analysis_provider_auth_states",
        ["state"],
        unique=True,
    )
    op.create_index(
        "ix_analysis_provider_auth_states_provider_id",
        "analysis_provider_auth_states",
        ["provider_id"],
        unique=False,
    )
    op.create_index(
        "ix_analysis_provider_auth_states_used",
        "analysis_provider_auth_states",
        ["used"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index("ix_analysis_provider_auth_states_used", table_name="analysis_provider_auth_states")
    op.drop_index("ix_analysis_provider_auth_states_provider_id", table_name="analysis_provider_auth_states")
    op.drop_index("ix_analysis_provider_auth_states_state", table_name="analysis_provider_auth_states")
    op.drop_table("analysis_provider_auth_states")

    op.drop_index("ix_analysis_provider_accounts_provider_id", table_name="analysis_provider_accounts")
    op.drop_table("analysis_provider_accounts")
