from __future__ import annotations

import argparse
import os
import sqlite3
from collections.abc import Iterable
from datetime import UTC, date, datetime, timedelta
from pathlib import Path
from typing import Any

from cryptography.fernet import Fernet
from sqlalchemy import Boolean, Date, DateTime, Float, Integer, MetaData, Table, create_engine, inspect, insert, text
from sqlalchemy.engine import Engine

from app.core.defaults import SCHEMA_DEFAULT_PAYCHECK_CADENCE

CUSTOMER_DATA_PREFIX = "cpf:v1:"


class CopyScriptError(RuntimeError):
    pass

# Insert parents before children; delete in reverse order for Postgres FK safety.
PHASE1_TABLES = [
    "user",
    "household_member",
    "onboarding_profile",
    "household_invite",
    "login_attempt",
    "plaid_item",
    "plaid_account_ignore",
    "account",
    "category",
    "category_rule",
    "transaction",
    "transaction_split",
    "plaid_webhook_event",
]
PHASE1_TRUNCATE_TABLES = [
    "plaid_webhook_event",
    "transaction_split",
    "transaction",
    "category_rule",
    "category",
    "account",
    "plaid_account_ignore",
    "plaid_item",
    "login_attempt",
    "household_invite",
    "onboarding_profile",
    "household_member",
    "user",
]

PHASE1_ENCRYPTED_COLUMNS = {
    "user": [
        "display_name",
        "household_name",
        "mfa_secret",
        "mfa_recovery_codes",
        "ai_guidance_snapshot",
        "cash_projection_calendar_token",
    ],
    "household_member": ["display_name", "mfa_secret", "mfa_recovery_codes"],
    "onboarding_profile": [
        "retirement_lifestyle_notes",
        "retirement_location_notes",
        "retirement_healthcare_notes",
        "retirement_income_notes",
        "retirement_debt_notes",
        "retirement_family_notes",
        "notes",
    ],
    "account": ["name", "institution"],
    "category_rule": ["match_text", "conditions_json"],
    "transaction": ["description", "merchant", "source_name", "notes", "plaid_metadata"],
    "transaction_split": ["notes"],
    "plaid_item": ["institution_name", "sync_cursor", "error_message"],
    "plaid_account_ignore": ["account_name", "institution_name"],
}


def utc_now() -> datetime:
    return datetime.now(UTC).replace(tzinfo=None, microsecond=0)


def _base_defaults() -> dict[str, dict[str, Any]]:
    now = utc_now()
    return {
        "user": {
            "is_admin": False,
            "mfa_enabled": False,
            "mfa_push_enabled": False,
            "mfa_preferred_method": "totp",
            "billing_status": "free",
            "selected_plan": "basic",
            "ai_provider": "openai",
            "ai_model": "gpt-5.5",
            "cash_projection_calendar_enabled": False,
            "cash_projection_default_horizon": "1m",
            "created_at": now,
            "updated_at": now,
        },
        "household_member": {
            "mfa_enabled": False,
            "mfa_push_enabled": False,
            "mfa_preferred_method": "totp",
            "role": "editor",
            "status": "active",
            "created_at": now,
            "updated_at": now,
        },
        "household_invite": {
            "role": "editor",
            "status": "pending",
            "expires_at": now + timedelta(days=14),
            "created_at": now,
            "updated_at": now,
        },
        "login_attempt": {
            "attempted_at": now,
            "success": False,
            "created_at": now,
            "updated_at": now,
        },
        "plaid_item": {
            "status": "connected",
            "access_token_encrypted": "",
            "created_at": now,
            "updated_at": now,
        },
        "plaid_account_ignore": {
            "created_at": now,
            "updated_at": now,
        },
        "plaid_webhook_event": {
            "webhook_type": "UNKNOWN",
            "webhook_code": "UNKNOWN",
            "status": "processing",
            "created_at": now,
            "updated_at": now,
        },
        "onboarding_profile": {
            "income_amount": 0.0,
            "income_basis": "take_home",
            "income_type": "salary",
            "income_frequency": "monthly",
            "paycheck_cadence": SCHEMA_DEFAULT_PAYCHECK_CADENCE,
            "hourly_hours_per_week": 40.0,
            "monthly_income": 0.0,
            "fixed_expenses": 0.0,
            "variable_expenses": 0.0,
            "additional_income_amount": 0.0,
            "additional_income_frequency": "annual",
            "planned_savings_contribution": 0.0,
            "planned_debt_payment": 0.0,
            "target_investment_contribution": 0.0,
            "tax_filing_status": "married_joint",
            "tax_gross_annual_income": 0.0,
            "tax_state_effective_rate": 0.0,
            "include_payroll_taxes": True,
            "retirement_enabled": False,
            "retirement_has_employer_plan": False,
            "retirement_employer_withheld": False,
            "retirement_has_personal_plan": False,
            "retirement_monthly_contribution": 0.0,
            "retirement_personal_monthly_contribution": 0.0,
            "created_at": now,
            "updated_at": now,
        },
        "account": {
            "account_type": "checking",
            "current_balance": 0.0,
            "cash_projection_role": "auto",
            "is_manual": True,
            "created_at": now,
            "updated_at": now,
        },
        "category": {
            "kind": "expense",
            "monthly_target": 0.0,
            "is_default": False,
            "created_at": now,
            "updated_at": now,
        },
        "category_rule": {
            "match_type": "contains",
            "rule_logic": "all",
            "created_at": now,
            "updated_at": now,
        },
        "transaction": {
            "transaction_type": "expense",
            "pending": False,
            "created_at": now,
            "updated_at": now,
        },
        "transaction_split": {
            "created_at": now,
            "updated_at": now,
        },
    }


def _fernet_from_env(name: str) -> Fernet:
    value = os.getenv(name)
    if not value:
        raise CopyScriptError(f"{name} is required before copying encrypted ClearPath data.")
    try:
        return Fernet(value.encode("ascii"))
    except Exception as exc:
        raise CopyScriptError(f"{name} must be a valid Fernet key.") from exc


def _decrypt_prefixed(value: str, fernet: Fernet, *, name: str) -> None:
    token = value[len(CUSTOMER_DATA_PREFIX) :]
    try:
        fernet.decrypt(token.encode("ascii"))
    except Exception as exc:
        raise CopyScriptError(f"Encrypted sample for {name} could not be decrypted with the configured key.") from exc


def _table_exists(conn: sqlite3.Connection, table: str) -> bool:
    row = conn.execute("SELECT name FROM sqlite_master WHERE type='table' AND name=?", (table,)).fetchone()
    return row is not None


def _sample_prefixed_values(conn: sqlite3.Connection, table: str, columns: Iterable[str]) -> list[tuple[str, str, str]]:
    if not _table_exists(conn, table):
        return []
    available = {row[1] for row in conn.execute(f'PRAGMA table_info("{table}")')}
    samples: list[tuple[str, str, str]] = []
    for column in columns:
        if column not in available:
            continue
        row = conn.execute(
            f'SELECT "{column}" FROM "{table}" WHERE "{column}" LIKE ? AND "{column}" IS NOT NULL LIMIT 1',
            (f"{CUSTOMER_DATA_PREFIX}%",),
        ).fetchone()
        if row and row[0]:
            samples.append((table, column, row[0]))
    return samples


def validate_encryption_keys(source: sqlite3.Connection) -> None:
    customer_samples: list[tuple[str, str, str]] = []
    for table, columns in PHASE1_ENCRYPTED_COLUMNS.items():
        customer_samples.extend(_sample_prefixed_values(source, table, columns))

    customer_fernet: Fernet | None = None
    if customer_samples:
        customer_fernet = _fernet_from_env("CUSTOMER_DATA_ENCRYPTION_KEY")
        table, column, value = customer_samples[0]
        _decrypt_prefixed(value, customer_fernet, name=f"{table}.{column}")

    if _table_exists(source, "plaid_item"):
        plaid_columns = set(source_columns(source, "plaid_item"))
        sync_cursor_samples = _sample_prefixed_values(source, "plaid_item", ["sync_cursor"])
        if sync_cursor_samples:
            customer_fernet = customer_fernet or _fernet_from_env("CUSTOMER_DATA_ENCRYPTION_KEY")
            table, column, value = sync_cursor_samples[0]
            _decrypt_prefixed(value, customer_fernet, name=f"{table}.{column}")

        if "access_token_encrypted" in plaid_columns:
            access_row = source.execute(
                'SELECT access_token_encrypted FROM "plaid_item" WHERE access_token_encrypted IS NOT NULL LIMIT 1'
            ).fetchone()
            if access_row and access_row[0]:
                plaid_fernet = _fernet_from_env("PLAID_TOKEN_ENCRYPTION_KEY")
                try:
                    plaid_fernet.decrypt(str(access_row[0]).encode("ascii"))
                except Exception as exc:
                    raise CopyScriptError("Plaid access token sample could not be decrypted with PLAID_TOKEN_ENCRYPTION_KEY.") from exc


def source_columns(source: sqlite3.Connection, table: str) -> list[str]:
    if not _table_exists(source, table):
        return []
    return [row[1] for row in source.execute(f'PRAGMA table_info("{table}")')]


def quote(identifier: str) -> str:
    return '"' + identifier.replace('"', '""') + '"'


def _parse_datetime(value: str) -> datetime:
    cleaned = value.strip().replace("Z", "+00:00")
    parsed = datetime.fromisoformat(cleaned)
    if parsed.tzinfo is not None:
        parsed = parsed.astimezone(UTC).replace(tzinfo=None)
    return parsed


def _parse_date(value: str) -> date:
    return date.fromisoformat(value.strip()[:10])


def coerce_value(value: Any, column) -> Any:
    if value is None:
        return None
    column_type = column.type
    if isinstance(column_type, Boolean):
        if isinstance(value, str):
            return value.strip().lower() in {"1", "true", "t", "yes", "y", "on"}
        return bool(value)
    if isinstance(column_type, DateTime):
        if isinstance(value, datetime):
            return value.replace(tzinfo=None)
        if isinstance(value, str):
            return _parse_datetime(value)
    if isinstance(column_type, Date) and not isinstance(column_type, DateTime):
        if isinstance(value, date) and not isinstance(value, datetime):
            return value
        if isinstance(value, str):
            return _parse_date(value)
    if isinstance(column_type, Integer):
        return int(value)
    if isinstance(column_type, Float):
        return float(value)
    return value


def reflected_table(target_engine: Engine, table_name: str) -> Table:
    metadata = MetaData()
    return Table(table_name, metadata, autoload_with=target_engine)


def row_for_target(source_row: sqlite3.Row, source_column_names: set[str], target_table: Table, defaults: dict[str, Any]) -> dict[str, Any]:
    row: dict[str, Any] = {}
    for column in target_table.columns:
        if column.name in source_column_names:
            raw_value = source_row[column.name]
        else:
            raw_value = defaults.get(column.name)
        if raw_value is None and not column.nullable and column.default is None and column.server_default is None:
            raise CopyScriptError(f"Missing required value for {target_table.name}.{column.name}; add a copy default or migrate source data first.")
        row[column.name] = coerce_value(raw_value, column)
    return row


def truncate_phase1_tables(target_engine: Engine) -> None:
    with target_engine.begin() as conn:
        for table in PHASE1_TRUNCATE_TABLES:
            if inspect(conn).has_table(table):
                conn.exec_driver_sql(f'DELETE FROM {quote(table)}')


def copy_table(source: sqlite3.Connection, target_engine: Engine, table: str) -> int:
    src_columns = source_columns(source, table)
    if not src_columns:
        return 0
    target_table = reflected_table(target_engine, table)
    target_column_names = {column.name for column in target_table.columns}
    selected_columns = [column for column in src_columns if column in target_column_names]
    if not selected_columns:
        return 0

    defaults = _base_defaults().get(table, {})
    source_column_set = set(selected_columns)
    source_sql = f'SELECT {", ".join(quote(c) for c in selected_columns)} FROM {quote(table)}'
    rows = [row_for_target(row, source_column_set, target_table, defaults) for row in source.execute(source_sql)]
    if rows:
        with target_engine.begin() as conn:
            conn.execute(insert(target_table), rows)
    return len(rows)


def copy_phase1(source: sqlite3.Connection, target_engine: Engine, *, truncate: bool) -> dict[str, int]:
    if truncate:
        truncate_phase1_tables(target_engine)
    return {table: copy_table(source, target_engine, table) for table in PHASE1_TABLES}


def main() -> None:
    parser = argparse.ArgumentParser(description="Copy Phase 1 ClearPath data from the Flask SQLite database.")
    parser.add_argument("--source", default=r"C:\Users\joshu\Documents\Codex\ClearPath Finance\clearpath_local.db")
    parser.add_argument("--target-url", default=os.getenv("DATABASE_URL", "sqlite:///./clearpath_dev.db"))
    parser.add_argument("--truncate", action="store_true", help="Delete Phase 1 target rows before inserting copied rows.")
    args = parser.parse_args()

    source_path = Path(args.source)
    if not source_path.exists():
        raise SystemExit(f"Source SQLite database does not exist: {source_path}")

    source = sqlite3.connect(source_path)
    source.row_factory = sqlite3.Row
    try:
        validate_encryption_keys(source)
        target_engine = create_engine(args.target_url, future=True)
        counts = copy_phase1(source, target_engine, truncate=args.truncate)
    except CopyScriptError as exc:
        raise SystemExit(str(exc)) from exc
    finally:
        source.close()

    for table, count in counts.items():
        print(f"{table}: {count}")


if __name__ == "__main__":
    main()
