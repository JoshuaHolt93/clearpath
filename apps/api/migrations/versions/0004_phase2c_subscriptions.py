"""phase 2c subscriptions and detection ignore ledger

Revision ID: 0004_phase2c_subscriptions
Revises: 0003_phase2b_plaid
Create Date: 2026-07-09
"""
from __future__ import annotations

from alembic import op
import sqlalchemy as sa

revision = "0004_phase2c_subscriptions"
down_revision = "0003_phase2b_plaid"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "subscription",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("user_id", sa.Integer(), sa.ForeignKey("user.id"), nullable=False),
        sa.Column("merchant_key", sa.String(length=140), nullable=False),
        sa.Column("name", sa.Text(), nullable=False),
        sa.Column("category", sa.String(length=80), nullable=False),
        sa.Column("service_category", sa.String(length=80), nullable=False),
        sa.Column("amount", sa.Float(), nullable=False),
        sa.Column("monthly_amount", sa.Float(), nullable=False),
        sa.Column("annual_amount", sa.Float(), nullable=False),
        sa.Column("cycle", sa.String(length=40), nullable=False),
        sa.Column("cycle_days", sa.Integer(), nullable=False),
        sa.Column("confidence", sa.Float(), nullable=False),
        sa.Column("status", sa.String(length=30), nullable=False),
        sa.Column("cancel_url", sa.Text(), nullable=True),
        sa.Column("replaceable", sa.Boolean(), nullable=False),
        sa.Column("first_seen", sa.Date(), nullable=True),
        sa.Column("last_seen", sa.Date(), nullable=True),
        sa.Column("next_charge_date", sa.Date(), nullable=True),
        sa.Column("evidence", sa.Text(), nullable=True),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column("is_manual", sa.Boolean(), nullable=False),
        sa.Column("cycle_is_manual", sa.Boolean(), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
    )
    op.create_index("ix_subscription_user_id", "subscription", ["user_id"])
    op.create_index("ix_subscription_user_merchant", "subscription", ["user_id", "merchant_key"])
    op.create_index("ix_subscription_user_status", "subscription", ["user_id", "status"])
    op.create_index("ix_subscription_user_next_charge", "subscription", ["user_id", "next_charge_date"])

    op.create_table(
        "subscription_transaction_ignore",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("user_id", sa.Integer(), sa.ForeignKey("user.id"), nullable=False),
        sa.Column("transaction_id", sa.Integer(), sa.ForeignKey("transaction.id"), nullable=False),
        sa.Column("subscription_id", sa.Integer(), sa.ForeignKey("subscription.id"), nullable=True),
        sa.Column("merchant_key", sa.String(length=140), nullable=True),
        sa.Column("amount", sa.Float(), nullable=True),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
    )
    op.create_index("ix_subscription_transaction_ignore_user_id", "subscription_transaction_ignore", ["user_id"])
    op.create_index("ix_subscription_transaction_ignore_transaction_id", "subscription_transaction_ignore", ["transaction_id"])
    op.create_index("ix_subscription_ignore_user_transaction", "subscription_transaction_ignore", ["user_id", "transaction_id"])
    op.create_index(
        "ix_subscription_ignore_user_merchant_amount",
        "subscription_transaction_ignore",
        ["user_id", "merchant_key", "amount"],
    )


def downgrade() -> None:
    op.drop_index("ix_subscription_ignore_user_merchant_amount", table_name="subscription_transaction_ignore")
    op.drop_index("ix_subscription_ignore_user_transaction", table_name="subscription_transaction_ignore")
    op.drop_index("ix_subscription_transaction_ignore_transaction_id", table_name="subscription_transaction_ignore")
    op.drop_index("ix_subscription_transaction_ignore_user_id", table_name="subscription_transaction_ignore")
    op.drop_table("subscription_transaction_ignore")

    op.drop_index("ix_subscription_user_next_charge", table_name="subscription")
    op.drop_index("ix_subscription_user_status", table_name="subscription")
    op.drop_index("ix_subscription_user_merchant", table_name="subscription")
    op.drop_index("ix_subscription_user_id", table_name="subscription")
    op.drop_table("subscription")
