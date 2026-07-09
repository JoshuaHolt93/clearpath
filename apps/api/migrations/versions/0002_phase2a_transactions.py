"""phase 2a transactions categories and imports

Revision ID: 0002_phase2a_transactions
Revises: 0001_phase1_auth_households
Create Date: 2026-07-02
"""
from __future__ import annotations

from alembic import op
import sqlalchemy as sa

revision = "0002_phase2a_transactions"
down_revision = "0001_phase1_auth_households"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "account",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("user_id", sa.Integer(), sa.ForeignKey("user.id"), nullable=False),
        sa.Column("name", sa.Text(), nullable=False),
        sa.Column("account_type", sa.String(length=50), nullable=False),
        sa.Column("institution", sa.Text(), nullable=True),
        sa.Column("current_balance", sa.Float(), nullable=False),
        sa.Column("cash_projection_role", sa.String(length=20), nullable=False),
        sa.Column("is_manual", sa.Boolean(), nullable=False),
        sa.Column("plaid_account_id", sa.String(length=140), nullable=True),
        sa.Column("plaid_item_id", sa.Integer(), nullable=True),
        sa.Column("mask", sa.String(length=20), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
    )
    op.create_index("ix_account_user_id", "account", ["user_id"])
    op.create_index("ix_account_plaid_account_id", "account", ["plaid_account_id"])
    op.create_index("ix_account_user_plaid_account", "account", ["user_id", "plaid_account_id"])
    op.create_index("ix_account_user_type", "account", ["user_id", "account_type"])

    op.create_table(
        "category",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("user_id", sa.Integer(), sa.ForeignKey("user.id"), nullable=True),
        sa.Column("name", sa.String(length=80), nullable=False),
        sa.Column("kind", sa.String(length=20), nullable=False),
        sa.Column("monthly_target", sa.Float(), nullable=False),
        sa.Column("is_default", sa.Boolean(), nullable=False),
        sa.Column("budget_group_key", sa.String(length=80), nullable=True),
        sa.Column("budget_sort_order", sa.Integer(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
    )
    op.create_index("ix_category_user_name", "category", ["user_id", "name"])
    op.create_index("ix_category_user_budget_sort", "category", ["user_id", "budget_sort_order"])

    op.create_table(
        "category_rule",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("user_id", sa.Integer(), sa.ForeignKey("user.id"), nullable=False),
        sa.Column("category_id", sa.Integer(), sa.ForeignKey("category.id"), nullable=False),
        sa.Column("match_text", sa.Text(), nullable=False),
        sa.Column("match_type", sa.String(length=20), nullable=False),
        sa.Column("rule_logic", sa.String(length=20), nullable=False),
        sa.Column("conditions_json", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
    )
    op.create_index("ix_category_rule_user_category", "category_rule", ["user_id", "category_id"])

    op.create_table(
        "transaction",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("user_id", sa.Integer(), sa.ForeignKey("user.id"), nullable=False),
        sa.Column("account_id", sa.Integer(), sa.ForeignKey("account.id"), nullable=True),
        sa.Column("category_id", sa.Integer(), sa.ForeignKey("category.id"), nullable=True),
        sa.Column("posted_date", sa.Date(), nullable=False),
        sa.Column("description", sa.Text(), nullable=False),
        sa.Column("merchant", sa.Text(), nullable=True),
        sa.Column("amount", sa.Float(), nullable=False),
        sa.Column("transaction_type", sa.String(length=20), nullable=False),
        sa.Column("source_name", sa.Text(), nullable=True),
        sa.Column("import_hash", sa.String(length=64), nullable=False),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column("plaid_transaction_id", sa.String(length=140), nullable=True),
        sa.Column("plaid_metadata", sa.Text(), nullable=True),
        sa.Column("pending", sa.Boolean(), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
    )
    op.create_index("ix_transaction_posted_date", "transaction", ["posted_date"])
    op.create_index("ix_transaction_import_hash", "transaction", ["import_hash"])
    op.create_index("ix_transaction_plaid_transaction_id", "transaction", ["plaid_transaction_id"])
    op.create_index("ix_transaction_user_posted_date", "transaction", ["user_id", "posted_date"])
    op.create_index("ix_transaction_user_import_hash", "transaction", ["user_id", "import_hash"])
    op.create_index("ix_transaction_user_plaid_transaction", "transaction", ["user_id", "plaid_transaction_id"])
    op.create_index("ix_transaction_user_account", "transaction", ["user_id", "account_id"])
    op.create_index("ix_transaction_user_category", "transaction", ["user_id", "category_id"])
    op.create_index("ix_transaction_user_category_date", "transaction", ["user_id", "category_id", "posted_date"])
    op.create_index("ix_transaction_user_account_date", "transaction", ["user_id", "account_id", "posted_date"])
    op.create_index("ix_transaction_user_date_id", "transaction", ["user_id", "posted_date", "id"])
    op.create_index("ix_transaction_user_amount_date", "transaction", ["user_id", "amount", "posted_date"])

    op.create_table(
        "transaction_split",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("user_id", sa.Integer(), sa.ForeignKey("user.id"), nullable=False),
        sa.Column("transaction_id", sa.Integer(), sa.ForeignKey("transaction.id"), nullable=False),
        sa.Column("category_id", sa.Integer(), sa.ForeignKey("category.id"), nullable=False),
        sa.Column("amount", sa.Float(), nullable=False),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
    )
    op.create_index("ix_transaction_split_user_transaction", "transaction_split", ["user_id", "transaction_id"])
    op.create_index("ix_transaction_split_user_category", "transaction_split", ["user_id", "category_id"])
    op.create_index("ix_transaction_split_user_category_transaction", "transaction_split", ["user_id", "category_id", "transaction_id"])


def downgrade() -> None:
    op.drop_index("ix_transaction_split_user_category_transaction", table_name="transaction_split")
    op.drop_index("ix_transaction_split_user_category", table_name="transaction_split")
    op.drop_index("ix_transaction_split_user_transaction", table_name="transaction_split")
    op.drop_table("transaction_split")

    op.drop_index("ix_transaction_user_amount_date", table_name="transaction")
    op.drop_index("ix_transaction_user_date_id", table_name="transaction")
    op.drop_index("ix_transaction_user_account_date", table_name="transaction")
    op.drop_index("ix_transaction_user_category_date", table_name="transaction")
    op.drop_index("ix_transaction_user_category", table_name="transaction")
    op.drop_index("ix_transaction_user_account", table_name="transaction")
    op.drop_index("ix_transaction_user_plaid_transaction", table_name="transaction")
    op.drop_index("ix_transaction_user_import_hash", table_name="transaction")
    op.drop_index("ix_transaction_user_posted_date", table_name="transaction")
    op.drop_index("ix_transaction_plaid_transaction_id", table_name="transaction")
    op.drop_index("ix_transaction_import_hash", table_name="transaction")
    op.drop_index("ix_transaction_posted_date", table_name="transaction")
    op.drop_table("transaction")

    op.drop_index("ix_category_rule_user_category", table_name="category_rule")
    op.drop_table("category_rule")

    op.drop_index("ix_category_user_budget_sort", table_name="category")
    op.drop_index("ix_category_user_name", table_name="category")
    op.drop_table("category")

    op.drop_index("ix_account_user_type", table_name="account")
    op.drop_index("ix_account_user_plaid_account", table_name="account")
    op.drop_index("ix_account_plaid_account_id", table_name="account")
    op.drop_index("ix_account_user_id", table_name="account")
    op.drop_table("account")
