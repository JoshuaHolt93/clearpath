"""phase 2b plaid items, ignores, webhook ledger

Revision ID: 0003_phase2b_plaid
Revises: 0002_phase2a_transactions
Create Date: 2026-07-09
"""
from __future__ import annotations

from alembic import op
import sqlalchemy as sa

revision = "0003_phase2b_plaid"
down_revision = "0002_phase2a_transactions"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "plaid_item",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("user_id", sa.Integer(), sa.ForeignKey("user.id"), nullable=False),
        sa.Column("plaid_item_id", sa.String(length=140), nullable=False),
        sa.Column("access_token_encrypted", sa.Text(), nullable=False),
        sa.Column("institution_name", sa.Text(), nullable=True),
        sa.Column("institution_id", sa.String(length=80), nullable=True),
        sa.Column("sync_cursor", sa.Text(), nullable=True),
        sa.Column("status", sa.String(length=40), nullable=False),
        sa.Column("last_synced_at", sa.DateTime(), nullable=True),
        sa.Column("error_code", sa.String(length=80), nullable=True),
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.Column("consent_acknowledged_at", sa.DateTime(), nullable=True),
        sa.Column("reconnect_required_at", sa.DateTime(), nullable=True),
        sa.Column("disconnected_at", sa.DateTime(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
    )
    op.create_index("ix_plaid_item_user_id", "plaid_item", ["user_id"])
    op.create_index("ix_plaid_item_plaid_item_id", "plaid_item", ["plaid_item_id"])
    op.create_index("ix_plaid_item_user_item", "plaid_item", ["user_id", "plaid_item_id"])
    op.create_index("ix_plaid_item_user_status", "plaid_item", ["user_id", "status"])

    op.create_table(
        "plaid_account_ignore",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("user_id", sa.Integer(), sa.ForeignKey("user.id"), nullable=False),
        sa.Column("plaid_item_id", sa.Integer(), sa.ForeignKey("plaid_item.id"), nullable=True),
        sa.Column("plaid_account_id", sa.String(length=140), nullable=False),
        sa.Column("account_name", sa.Text(), nullable=True),
        sa.Column("institution_name", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
    )
    op.create_index("ix_plaid_account_ignore_user_id", "plaid_account_ignore", ["user_id"])
    op.create_index("ix_plaid_account_ignore_plaid_account_id", "plaid_account_ignore", ["plaid_account_id"])
    op.create_index("ix_plaid_account_ignore_user_account", "plaid_account_ignore", ["user_id", "plaid_account_id"])

    op.create_table(
        "plaid_webhook_event",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("idempotency_key", sa.String(length=255), nullable=False),
        sa.Column("plaid_item_id", sa.Integer(), sa.ForeignKey("plaid_item.id"), nullable=True),
        sa.Column("webhook_type", sa.String(length=80), nullable=False),
        sa.Column("webhook_code", sa.String(length=120), nullable=False),
        sa.Column("status", sa.String(length=30), nullable=False),
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.Column("processed_at", sa.DateTime(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
    )
    op.create_index("ix_plaid_webhook_event_idempotency_key", "plaid_webhook_event", ["idempotency_key"], unique=True)
    op.create_index("ix_plaid_webhook_event_webhook_type", "plaid_webhook_event", ["webhook_type"])
    op.create_index("ix_plaid_webhook_event_webhook_code", "plaid_webhook_event", ["webhook_code"])
    op.create_index("ix_plaid_webhook_event_status", "plaid_webhook_event", ["status"])
    op.create_index("ix_plaid_webhook_event_status_created", "plaid_webhook_event", ["status", "created_at"])
    op.create_index("ix_plaid_webhook_event_type_code", "plaid_webhook_event", ["webhook_type", "webhook_code"])
    op.create_index("ix_plaid_webhook_event_item_created", "plaid_webhook_event", ["plaid_item_id", "created_at"])

    # account.plaid_item_id existed as a bare Integer in 0002 (plaid_item did not
    # exist yet). Promote it to a real foreign key; batch mode handles SQLite's
    # table rebuild and emits a plain ALTER on Postgres.
    with op.batch_alter_table("account") as batch_op:
        batch_op.create_foreign_key("fk_account_plaid_item_id_plaid_item", "plaid_item", ["plaid_item_id"], ["id"])


def downgrade() -> None:
    with op.batch_alter_table("account") as batch_op:
        batch_op.drop_constraint("fk_account_plaid_item_id_plaid_item", type_="foreignkey")

    op.drop_index("ix_plaid_webhook_event_item_created", table_name="plaid_webhook_event")
    op.drop_index("ix_plaid_webhook_event_type_code", table_name="plaid_webhook_event")
    op.drop_index("ix_plaid_webhook_event_status_created", table_name="plaid_webhook_event")
    op.drop_index("ix_plaid_webhook_event_status", table_name="plaid_webhook_event")
    op.drop_index("ix_plaid_webhook_event_webhook_code", table_name="plaid_webhook_event")
    op.drop_index("ix_plaid_webhook_event_webhook_type", table_name="plaid_webhook_event")
    op.drop_index("ix_plaid_webhook_event_idempotency_key", table_name="plaid_webhook_event")
    op.drop_table("plaid_webhook_event")

    op.drop_index("ix_plaid_account_ignore_user_account", table_name="plaid_account_ignore")
    op.drop_index("ix_plaid_account_ignore_plaid_account_id", table_name="plaid_account_ignore")
    op.drop_index("ix_plaid_account_ignore_user_id", table_name="plaid_account_ignore")
    op.drop_table("plaid_account_ignore")

    op.drop_index("ix_plaid_item_user_status", table_name="plaid_item")
    op.drop_index("ix_plaid_item_user_item", table_name="plaid_item")
    op.drop_index("ix_plaid_item_plaid_item_id", table_name="plaid_item")
    op.drop_index("ix_plaid_item_user_id", table_name="plaid_item")
    op.drop_table("plaid_item")
