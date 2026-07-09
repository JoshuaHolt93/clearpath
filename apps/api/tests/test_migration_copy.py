from __future__ import annotations

import os
import sqlite3
import subprocess
import sys
import tempfile
from pathlib import Path

import pytest
from alembic import command
from alembic.config import Config
from cryptography.fernet import Fernet
from sqlalchemy import create_engine, text

from scripts.copy_from_flask_sqlite import CUSTOMER_DATA_PREFIX, CopyScriptError, copy_phase1, validate_encryption_keys

API_ROOT = Path(__file__).resolve().parents[1]
PHASE1_TABLES = [
    "plaid_webhook_event",
    "subscription_transaction_ignore",
    "subscription",
    "ai_usage_log",
    "loan_plan",
    "cash_projection_recurring_ignore",
    "insight",
    "monthly_budget_category_snapshot",
    "monthly_budget_snapshot",
    "monthly_plan",
    "goal",
    "forecast_item",
    "recurring_forecast_template",
    "variable_expense_item",
    "fixed_expense_item",
    "transaction_split",
    "transaction",
    "category_rule",
    "category",
    "account",
    "plaid_account_ignore",
    "plaid_item",
    "household_invite",
    "onboarding_profile",
    "household_member",
    "login_attempt",
    "user",
    "alembic_version",
]


def encrypted_customer_value(key: str, value: str) -> str:
    token = Fernet(key.encode("ascii")).encrypt(value.encode("utf-8")).decode("ascii")
    return f"{CUSTOMER_DATA_PREFIX}{token}"


def plaid_token_value(key: str, value: str) -> str:
    return Fernet(key.encode("ascii")).encrypt(value.encode("utf-8")).decode("ascii")


def create_sample_flask_sqlite(path: Path, *, customer_key: str, plaid_key: str) -> None:
    conn = sqlite3.connect(path)
    try:
        conn.executescript(
            """
            CREATE TABLE "user" (
                id INTEGER PRIMARY KEY,
                email TEXT NOT NULL,
                password_hash TEXT NOT NULL,
                display_name TEXT,
                household_name TEXT,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL
            );
            CREATE TABLE household_member (
                id INTEGER PRIMARY KEY,
                owner_user_id INTEGER NOT NULL,
                invited_by_user_id INTEGER NOT NULL,
                email TEXT NOT NULL,
                password_hash TEXT NOT NULL,
                display_name TEXT,
                role TEXT NOT NULL,
                status TEXT NOT NULL,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL
            );
            CREATE TABLE onboarding_profile (
                id INTEGER PRIMARY KEY,
                user_id INTEGER NOT NULL,
                income_amount REAL,
                monthly_income REAL,
                include_payroll_taxes INTEGER,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL
            );
            CREATE TABLE household_invite (
                id INTEGER PRIMARY KEY,
                owner_user_id INTEGER NOT NULL,
                invited_by_user_id INTEGER NOT NULL,
                accepted_member_id INTEGER,
                email TEXT NOT NULL,
                token_hash TEXT NOT NULL,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL
            );
            CREATE TABLE login_attempt (
                id INTEGER PRIMARY KEY,
                key TEXT NOT NULL,
                attempted_at TEXT NOT NULL,
                success INTEGER NOT NULL,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL
            );
            CREATE TABLE account (
                id INTEGER PRIMARY KEY,
                user_id INTEGER NOT NULL,
                name TEXT NOT NULL,
                account_type TEXT,
                institution TEXT,
                current_balance REAL,
                is_manual INTEGER,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL
            );
            CREATE TABLE category (
                id INTEGER PRIMARY KEY,
                user_id INTEGER,
                name TEXT NOT NULL,
                kind TEXT,
                monthly_target REAL,
                is_default INTEGER,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL
            );
            CREATE TABLE category_rule (
                id INTEGER PRIMARY KEY,
                user_id INTEGER NOT NULL,
                category_id INTEGER NOT NULL,
                match_text TEXT NOT NULL,
                match_type TEXT,
                conditions_json TEXT,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL
            );
            CREATE TABLE "transaction" (
                id INTEGER PRIMARY KEY,
                user_id INTEGER NOT NULL,
                account_id INTEGER,
                category_id INTEGER,
                posted_date TEXT NOT NULL,
                description TEXT NOT NULL,
                merchant TEXT,
                amount REAL NOT NULL,
                source_name TEXT,
                import_hash TEXT NOT NULL,
                notes TEXT,
                pending INTEGER,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL
            );
            CREATE TABLE transaction_split (
                id INTEGER PRIMARY KEY,
                user_id INTEGER NOT NULL,
                transaction_id INTEGER NOT NULL,
                category_id INTEGER NOT NULL,
                amount REAL NOT NULL,
                notes TEXT,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL
            );
            CREATE TABLE plaid_item (
                id INTEGER PRIMARY KEY,
                user_id INTEGER NOT NULL,
                plaid_item_id TEXT NOT NULL,
                access_token_encrypted TEXT,
                institution_name TEXT,
                sync_cursor TEXT,
                status TEXT,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL
            );
            CREATE TABLE plaid_account_ignore (
                id INTEGER PRIMARY KEY,
                user_id INTEGER NOT NULL,
                plaid_item_id INTEGER,
                plaid_account_id TEXT NOT NULL,
                account_name TEXT,
                institution_name TEXT,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL
            );
            CREATE TABLE plaid_webhook_event (
                id INTEGER PRIMARY KEY,
                idempotency_key TEXT NOT NULL,
                plaid_item_id INTEGER,
                webhook_type TEXT NOT NULL,
                webhook_code TEXT NOT NULL,
                status TEXT NOT NULL,
                processed_at TEXT,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL
            );
            CREATE TABLE subscription (
                id INTEGER PRIMARY KEY,
                user_id INTEGER NOT NULL,
                merchant_key TEXT NOT NULL,
                name TEXT NOT NULL,
                cycle TEXT,
                monthly_amount REAL,
                status TEXT,
                cancel_url TEXT,
                is_manual INTEGER,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL
            );
            CREATE TABLE subscription_transaction_ignore (
                id INTEGER PRIMARY KEY,
                user_id INTEGER NOT NULL,
                transaction_id INTEGER NOT NULL,
                subscription_id INTEGER,
                merchant_key TEXT,
                amount REAL,
                description TEXT,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL
            );
            CREATE TABLE fixed_expense_item (
                id INTEGER PRIMARY KEY,
                user_id INTEGER NOT NULL,
                name TEXT NOT NULL,
                amount REAL,
                start_date TEXT,
                frequency TEXT,
                category_label TEXT,
                is_loan INTEGER,
                notes TEXT,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL
            );
            CREATE TABLE goal (
                id INTEGER PRIMARY KEY,
                user_id INTEGER NOT NULL,
                name TEXT NOT NULL,
                goal_type TEXT NOT NULL,
                target_amount REAL NOT NULL,
                current_amount REAL,
                monthly_contribution REAL,
                target_date TEXT,
                fixed_expense_item_id INTEGER,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL
            );
            CREATE TABLE monthly_plan (
                id INTEGER PRIMARY KEY,
                user_id INTEGER NOT NULL,
                month TEXT NOT NULL,
                income REAL,
                fixed_expenses REAL,
                planned_savings REAL,
                planned_debt_payment REAL,
                safe_to_spend_target REAL,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL
            );
            CREATE TABLE insight (
                id INTEGER PRIMARY KEY,
                user_id INTEGER NOT NULL,
                month TEXT NOT NULL,
                title TEXT NOT NULL,
                body TEXT NOT NULL,
                level TEXT,
                insight_type TEXT NOT NULL,
                is_active INTEGER,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL
            );
            CREATE TABLE loan_plan (
                id INTEGER PRIMARY KEY,
                user_id INTEGER NOT NULL,
                fixed_expense_item_id INTEGER NOT NULL,
                loan_type TEXT,
                principal_balance REAL,
                annual_interest_rate REAL,
                term_months INTEGER,
                regular_payment REAL,
                selected_scenario TEXT,
                notes TEXT,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL
            );
            """
        )
        now = "2026-07-02T10:11:12"
        conn.execute(
            'INSERT INTO "user" (id, email, password_hash, display_name, household_name, created_at, updated_at) VALUES (?, ?, ?, ?, ?, ?, ?)',
            (1, "owner@example.com", "scrypt:32768:8:1$fake$hash", encrypted_customer_value(customer_key, "Owner Name"), encrypted_customer_value(customer_key, "Owner Household"), now, now),
        )
        conn.execute(
            "INSERT INTO household_member (id, owner_user_id, invited_by_user_id, email, password_hash, display_name, role, status, created_at, updated_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (10, 1, 1, "shared@example.com", "scrypt:32768:8:1$fake$hash", encrypted_customer_value(customer_key, "Shared Name"), "viewer", "active", now, now),
        )
        conn.execute(
            "INSERT INTO onboarding_profile (id, user_id, income_amount, monthly_income, include_payroll_taxes, created_at, updated_at) VALUES (?, ?, ?, ?, ?, ?, ?)",
            (100, 1, 5000.0, 5000.0, 1, now, now),
        )
        conn.execute(
            "INSERT INTO household_invite (id, owner_user_id, invited_by_user_id, accepted_member_id, email, token_hash, created_at, updated_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
            (200, 1, 1, 10, "accepted@example.com", "abc123", now, now),
        )
        conn.execute(
            "INSERT INTO login_attempt (id, key, attempted_at, success, created_at, updated_at) VALUES (?, ?, ?, ?, ?, ?)",
            (300, "login:owner@example.com", now, 0, now, now),
        )
        conn.execute(
            "INSERT INTO account (id, user_id, name, account_type, institution, current_balance, is_manual, created_at, updated_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (500, 1, encrypted_customer_value(customer_key, "Main Checking"), "checking", encrypted_customer_value(customer_key, "Test Bank"), 123.45, 1, now, now),
        )
        conn.execute(
            "INSERT INTO category (id, user_id, name, kind, monthly_target, is_default, created_at, updated_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
            (600, 1, "Groceries", "expense", 600.0, 0, now, now),
        )
        conn.execute(
            "INSERT INTO category_rule (id, user_id, category_id, match_text, match_type, conditions_json, created_at, updated_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
            (
                700,
                1,
                600,
                encrypted_customer_value(customer_key, "kroger"),
                "contains",
                encrypted_customer_value(customer_key, '[{"field":"description","operator":"contains","value":"kroger","value_secondary":"","group":"primary","join":"and"}]'),
                now,
                now,
            ),
        )
        conn.execute(
            'INSERT INTO "transaction" (id, user_id, account_id, category_id, posted_date, description, merchant, amount, source_name, import_hash, notes, pending, created_at, updated_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)',
            (
                800,
                1,
                500,
                600,
                "2026-07-02",
                encrypted_customer_value(customer_key, "Kroger Store 214"),
                encrypted_customer_value(customer_key, "Kroger Store 214"),
                -42.25,
                encrypted_customer_value(customer_key, "Main Checking"),
                "hash-800",
                encrypted_customer_value(customer_key, "paper receipt"),
                0,
                now,
                now,
            ),
        )
        conn.execute(
            "INSERT INTO transaction_split (id, user_id, transaction_id, category_id, amount, notes, created_at, updated_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
            (900, 1, 800, 600, 42.25, encrypted_customer_value(customer_key, "split note"), now, now),
        )
        conn.execute(
            "INSERT INTO plaid_item (id, user_id, plaid_item_id, access_token_encrypted, institution_name, sync_cursor, status, created_at, updated_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (
                400,
                1,
                "item-flask-1",
                plaid_token_value(plaid_key, "access-sandbox-token"),
                encrypted_customer_value(customer_key, "Flask Test Bank"),
                encrypted_customer_value(customer_key, "cursor-value"),
                "connected",
                now,
                now,
            ),
        )
        conn.execute(
            "INSERT INTO plaid_account_ignore (id, user_id, plaid_item_id, plaid_account_id, account_name, institution_name, created_at, updated_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
            (
                410,
                1,
                400,
                "acct-ignored-1",
                encrypted_customer_value(customer_key, "Old Savings"),
                encrypted_customer_value(customer_key, "Flask Test Bank"),
                now,
                now,
            ),
        )
        conn.execute(
            "INSERT INTO plaid_webhook_event (id, idempotency_key, plaid_item_id, webhook_type, webhook_code, status, processed_at, created_at, updated_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (420, "idem-key-1", 400, "TRANSACTIONS", "SYNC_UPDATES_AVAILABLE", "processed", now, now, now),
        )
        conn.execute(
            "INSERT INTO subscription (id, user_id, merchant_key, name, cycle, monthly_amount, status, cancel_url, is_manual, created_at, updated_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (
                1000,
                1,
                "netflix",
                encrypted_customer_value(customer_key, "Netflix"),
                "Monthly",
                18.99,
                "active",
                encrypted_customer_value(customer_key, "https://www.netflix.com/cancelplan"),
                0,
                now,
                now,
            ),
        )
        conn.execute(
            "INSERT INTO subscription_transaction_ignore (id, user_id, transaction_id, subscription_id, merchant_key, amount, description, created_at, updated_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (1100, 1, 800, 1000, "netflix", -18.99, encrypted_customer_value(customer_key, "NETFLIX.COM"), now, now),
        )
        conn.execute(
            "INSERT INTO fixed_expense_item (id, user_id, name, amount, start_date, frequency, category_label, is_loan, notes, created_at, updated_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (
                1200,
                1,
                encrypted_customer_value(customer_key, "Mortgage Payment"),
                1800.0,
                "2026-01-01",
                "monthly",
                "Mortgage/Rent",
                1,
                encrypted_customer_value(customer_key, "primary residence"),
                now,
                now,
            ),
        )
        conn.execute(
            "INSERT INTO goal (id, user_id, name, goal_type, target_amount, current_amount, monthly_contribution, fixed_expense_item_id, created_at, updated_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (1300, 1, encrypted_customer_value(customer_key, "Emergency Fund"), "savings", 10000.0, 2500.0, 250.0, None, now, now),
        )
        conn.execute(
            "INSERT INTO monthly_plan (id, user_id, month, income, fixed_expenses, planned_savings, planned_debt_payment, safe_to_spend_target, created_at, updated_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (1400, 1, "2026-07-01", 5000.0, 1800.0, 500.0, 300.0, 1200.0, now, now),
        )
        conn.execute(
            "INSERT INTO insight (id, user_id, month, title, body, level, insight_type, is_active, created_at, updated_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (
                1500,
                1,
                "2026-07-01",
                encrypted_customer_value(customer_key, "Spending is on track"),
                encrypted_customer_value(customer_key, "You are under budget this month."),
                "info",
                "on_track",
                1,
                now,
                now,
            ),
        )
        conn.execute(
            "INSERT INTO loan_plan (id, user_id, fixed_expense_item_id, loan_type, principal_balance, annual_interest_rate, term_months, regular_payment, selected_scenario, notes, created_at, updated_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (1600, 1, 1200, "mortgage", 285000.0, 5.875, 360, 1800.0, "base", encrypted_customer_value(customer_key, "30yr fixed"), now, now),
        )
        conn.commit()
    finally:
        conn.close()


def test_validate_encryption_keys_checks_plaid_sync_cursor():
    customer_key = Fernet.generate_key().decode("ascii")
    plaid_key = Fernet.generate_key().decode("ascii")
    original_customer_key = os.environ.get("CUSTOMER_DATA_ENCRYPTION_KEY")
    original_plaid_key = os.environ.get("PLAID_TOKEN_ENCRYPTION_KEY")
    temp = tempfile.NamedTemporaryFile(delete=False, suffix=".db")
    temp.close()
    source = Path(temp.name)
    conn = sqlite3.connect(source)
    try:
        conn.execute("CREATE TABLE plaid_item (id INTEGER PRIMARY KEY, sync_cursor TEXT)")
        conn.execute("INSERT INTO plaid_item (id, sync_cursor) VALUES (?, ?)", (1, encrypted_customer_value(customer_key, "cursor")))
        conn.commit()
        os.environ["CUSTOMER_DATA_ENCRYPTION_KEY"] = customer_key
        os.environ["PLAID_TOKEN_ENCRYPTION_KEY"] = plaid_key
        validate_encryption_keys(conn)

        os.environ["CUSTOMER_DATA_ENCRYPTION_KEY"] = Fernet.generate_key().decode("ascii")
        try:
            validate_encryption_keys(conn)
        except CopyScriptError as exc:
            assert "plaid_item.sync_cursor" in str(exc)
        else:
            raise AssertionError("Expected plaid_item.sync_cursor validation to fail with the wrong customer key.")
    finally:
        conn.close()
        source.unlink(missing_ok=True)
        if original_customer_key is None:
            os.environ.pop("CUSTOMER_DATA_ENCRYPTION_KEY", None)
        else:
            os.environ["CUSTOMER_DATA_ENCRYPTION_KEY"] = original_customer_key
        if original_plaid_key is None:
            os.environ.pop("PLAID_TOKEN_ENCRYPTION_KEY", None)
        else:
            os.environ["PLAID_TOKEN_ENCRYPTION_KEY"] = original_plaid_key



def test_copy_phase1_supplies_defaults_and_truncates_with_sqlite():
    from app.models import Base

    customer_key = Fernet.generate_key().decode("ascii")
    plaid_key = Fernet.generate_key().decode("ascii")
    original_customer_key = os.environ.get("CUSTOMER_DATA_ENCRYPTION_KEY")
    original_plaid_key = os.environ.get("PLAID_TOKEN_ENCRYPTION_KEY")
    source_temp = tempfile.NamedTemporaryFile(delete=False, suffix=".db")
    target_temp = tempfile.NamedTemporaryFile(delete=False, suffix=".db")
    source_temp.close()
    target_temp.close()
    source_path = Path(source_temp.name)
    target_path = Path(target_temp.name)
    source_conn: sqlite3.Connection | None = None
    target_engine = None
    try:
        os.environ["CUSTOMER_DATA_ENCRYPTION_KEY"] = customer_key
        os.environ["PLAID_TOKEN_ENCRYPTION_KEY"] = plaid_key
        create_sample_flask_sqlite(source_path, customer_key=customer_key, plaid_key=plaid_key)
        source_conn = sqlite3.connect(source_path)
        source_conn.row_factory = sqlite3.Row
        target_engine = create_engine(f"sqlite:///{target_path.as_posix()}", future=True)
        Base.metadata.create_all(target_engine)

        counts = copy_phase1(source_conn, target_engine, truncate=True)
        assert counts == {
            "user": 1,
            "household_member": 1,
            "onboarding_profile": 1,
            "household_invite": 1,
            "login_attempt": 1,
            "plaid_item": 1,
            "plaid_account_ignore": 1,
            "account": 1,
            "category": 1,
            "category_rule": 1,
            "transaction": 1,
            "transaction_split": 1,
            "fixed_expense_item": 1,
            "variable_expense_item": 0,
            "recurring_forecast_template": 0,
            "forecast_item": 0,
            "goal": 1,
            "monthly_plan": 1,
            "monthly_budget_snapshot": 0,
            "monthly_budget_category_snapshot": 0,
            "insight": 1,
            "cash_projection_recurring_ignore": 0,
            "loan_plan": 1,
            "ai_usage_log": 0,
            "subscription": 1,
            "subscription_transaction_ignore": 1,
            "plaid_webhook_event": 1,
        }
        second_counts = copy_phase1(source_conn, target_engine, truncate=True)
        assert second_counts == counts

        with target_engine.begin() as conn:
            row = conn.execute(text('SELECT is_admin, mfa_enabled, selected_plan FROM "user" WHERE id = 1')).one()
            profile = conn.execute(text("SELECT include_payroll_taxes, paycheck_cadence FROM onboarding_profile WHERE id = 100")).one()
            account = conn.execute(text("SELECT cash_projection_role, is_manual FROM account WHERE id = 500")).one()
            transaction = conn.execute(text('SELECT pending, transaction_type FROM "transaction" WHERE id = 800')).one()
        assert row.is_admin in {False, 0}
        assert row.mfa_enabled in {False, 0}
        assert row.selected_plan == "basic"
        assert profile.include_payroll_taxes in {True, 1}
        assert profile.paycheck_cadence == "semimonthly"
        assert account.cash_projection_role == "auto"
        assert account.is_manual in {True, 1}
        assert transaction.pending in {False, 0}
        assert transaction.transaction_type == "expense"
    finally:
        if source_conn is not None:
            source_conn.close()
        if target_engine is not None:
            target_engine.dispose()
        source_path.unlink(missing_ok=True)
        target_path.unlink(missing_ok=True)
        if original_customer_key is None:
            os.environ.pop("CUSTOMER_DATA_ENCRYPTION_KEY", None)
        else:
            os.environ["CUSTOMER_DATA_ENCRYPTION_KEY"] = original_customer_key
        if original_plaid_key is None:
            os.environ.pop("PLAID_TOKEN_ENCRYPTION_KEY", None)
        else:
            os.environ["PLAID_TOKEN_ENCRYPTION_KEY"] = original_plaid_key

@pytest.mark.integration
@pytest.mark.skipif(not os.getenv("POSTGRES_TEST_DATABASE_URL"), reason="POSTGRES_TEST_DATABASE_URL is required for the real-Postgres migration/copy gate.")
def test_alembic_upgrade_and_sqlite_copy_against_real_postgres(tmp_path):
    postgres_url = os.environ["POSTGRES_TEST_DATABASE_URL"]
    customer_key = Fernet.generate_key().decode("ascii")
    plaid_key = Fernet.generate_key().decode("ascii")
    source = tmp_path / "flask_source.db"
    create_sample_flask_sqlite(source, customer_key=customer_key, plaid_key=plaid_key)

    engine = create_engine(postgres_url, future=True)
    with engine.begin() as conn:
        for table in PHASE1_TABLES:
            conn.exec_driver_sql(f'DROP TABLE IF EXISTS "{table}" CASCADE')

    alembic_cfg = Config(str(API_ROOT / "alembic.ini"))
    alembic_cfg.set_main_option("script_location", str(API_ROOT / "migrations"))
    alembic_cfg.set_main_option("sqlalchemy.url", postgres_url)
    previous_database_url = os.environ.get("DATABASE_URL")
    os.environ["DATABASE_URL"] = postgres_url
    try:
        command.upgrade(alembic_cfg, "head")
    finally:
        if previous_database_url is None:
            os.environ.pop("DATABASE_URL", None)
        else:
            os.environ["DATABASE_URL"] = previous_database_url

    env = os.environ.copy()
    env["CUSTOMER_DATA_ENCRYPTION_KEY"] = customer_key
    env["PLAID_TOKEN_ENCRYPTION_KEY"] = plaid_key
    command_line = [sys.executable, str(API_ROOT / "scripts" / "copy_from_flask_sqlite.py"), "--source", str(source), "--target-url", postgres_url, "--truncate"]
    first = subprocess.run(command_line, cwd=API_ROOT, env=env, text=True, capture_output=True, check=True)
    assert "user: 1" in first.stdout
    assert "household_member: 1" in first.stdout
    assert "onboarding_profile: 1" in first.stdout
    assert "household_invite: 1" in first.stdout
    assert "login_attempt: 1" in first.stdout
    assert "account: 1" in first.stdout
    assert "category: 1" in first.stdout
    assert "category_rule: 1" in first.stdout
    assert "transaction: 1" in first.stdout
    assert "transaction_split: 1" in first.stdout
    assert "plaid_item: 1" in first.stdout
    assert "plaid_account_ignore: 1" in first.stdout
    assert "plaid_webhook_event: 1" in first.stdout
    assert "subscription: 1" in first.stdout
    assert "subscription_transaction_ignore: 1" in first.stdout
    assert "fixed_expense_item: 1" in first.stdout
    assert "goal: 1" in first.stdout
    assert "monthly_plan: 1" in first.stdout
    assert "insight: 1" in first.stdout
    assert "loan_plan: 1" in first.stdout

    subprocess.run(command_line, cwd=API_ROOT, env=env, text=True, capture_output=True, check=True)

    with engine.begin() as conn:
        assert conn.scalar(text('SELECT count(*) FROM "user"')) == 1
        assert conn.scalar(text("SELECT count(*) FROM household_member")) == 1
        assert conn.scalar(text("SELECT count(*) FROM onboarding_profile")) == 1
        assert conn.scalar(text("SELECT count(*) FROM household_invite")) == 1
        assert conn.scalar(text("SELECT count(*) FROM login_attempt")) == 1
        assert conn.scalar(text("SELECT count(*) FROM account")) == 1
        assert conn.scalar(text("SELECT count(*) FROM category")) == 1
        assert conn.scalar(text("SELECT count(*) FROM category_rule")) == 1
        assert conn.scalar(text('SELECT count(*) FROM "transaction"')) == 1
        assert conn.scalar(text("SELECT count(*) FROM transaction_split")) == 1
        assert conn.scalar(text("SELECT count(*) FROM plaid_item")) == 1
        assert conn.scalar(text("SELECT count(*) FROM plaid_account_ignore")) == 1
        assert conn.scalar(text("SELECT count(*) FROM plaid_webhook_event")) == 1
        assert conn.scalar(text("SELECT count(*) FROM subscription")) == 1
        assert conn.scalar(text("SELECT count(*) FROM subscription_transaction_ignore")) == 1
        assert conn.scalar(text("SELECT count(*) FROM fixed_expense_item")) == 1
        assert conn.scalar(text("SELECT count(*) FROM goal")) == 1
        assert conn.scalar(text("SELECT count(*) FROM monthly_plan")) == 1
        assert conn.scalar(text("SELECT count(*) FROM insight")) == 1
        assert conn.scalar(text("SELECT count(*) FROM loan_plan")) == 1
        goal_row = conn.execute(text("SELECT name, target_amount FROM goal WHERE id = 1300")).one()
        loan_row = conn.execute(
            text("SELECT fixed_expense_item_id, annual_interest_rate, term_unit_preference FROM loan_plan WHERE id = 1600")
        ).one()
        subscription_row = conn.execute(text("SELECT name, replaceable, monthly_amount FROM subscription WHERE id = 1000")).one()
        plaid_row = conn.execute(text("SELECT access_token_encrypted, sync_cursor, status FROM plaid_item WHERE id = 400")).one()
        user_row = conn.execute(text('SELECT display_name, is_admin, mfa_enabled FROM "user" WHERE id = 1')).one()
        profile_row = conn.execute(text("SELECT include_payroll_taxes, paycheck_cadence FROM onboarding_profile WHERE id = 100")).one()
        account_row = conn.execute(text("SELECT name, is_manual FROM account WHERE id = 500")).one()
        transaction_row = conn.execute(text('SELECT description, pending FROM "transaction" WHERE id = 800')).one()

    decrypted_name = Fernet(customer_key.encode("ascii")).decrypt(user_row.display_name[len(CUSTOMER_DATA_PREFIX) :].encode("ascii")).decode("utf-8")
    decrypted_account_name = Fernet(customer_key.encode("ascii")).decrypt(account_row.name[len(CUSTOMER_DATA_PREFIX) :].encode("ascii")).decode("utf-8")
    decrypted_description = Fernet(customer_key.encode("ascii")).decrypt(transaction_row.description[len(CUSTOMER_DATA_PREFIX) :].encode("ascii")).decode("utf-8")
    assert decrypted_name == "Owner Name"
    assert decrypted_account_name == "Main Checking"
    assert decrypted_description == "Kroger Store 214"
    assert user_row.is_admin is False
    assert user_row.mfa_enabled is False
    assert profile_row.include_payroll_taxes is True
    assert profile_row.paycheck_cadence == "semimonthly"
    assert account_row.is_manual is True
    assert transaction_row.pending is False
    # Plaid ciphertext must copy verbatim: the access token decrypts with the
    # Plaid key and the sync cursor with the customer-data key.
    decrypted_access_token = Fernet(plaid_key.encode("ascii")).decrypt(plaid_row.access_token_encrypted.encode("ascii")).decode("utf-8")
    decrypted_cursor = Fernet(customer_key.encode("ascii")).decrypt(plaid_row.sync_cursor[len(CUSTOMER_DATA_PREFIX) :].encode("ascii")).decode("utf-8")
    assert decrypted_access_token == "access-sandbox-token"
    assert decrypted_cursor == "cursor-value"
    assert plaid_row.status == "connected"
    decrypted_subscription_name = Fernet(customer_key.encode("ascii")).decrypt(subscription_row.name[len(CUSTOMER_DATA_PREFIX) :].encode("ascii")).decode("utf-8")
    assert decrypted_subscription_name == "Netflix"
    # replaceable is absent from the source, so the copy default (True) applies.
    assert subscription_row.replaceable is True
    assert subscription_row.monthly_amount == 18.99
    decrypted_goal_name = Fernet(customer_key.encode("ascii")).decrypt(goal_row.name[len(CUSTOMER_DATA_PREFIX) :].encode("ascii")).decode("utf-8")
    assert decrypted_goal_name == "Emergency Fund"
    assert goal_row.target_amount == 10000.0
    assert loan_row.fixed_expense_item_id == 1200
    assert loan_row.annual_interest_rate == 5.875
    # term_unit_preference is absent from the source, so the copy default applies.
    assert loan_row.term_unit_preference == "months"
