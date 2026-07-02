from __future__ import annotations

import tempfile
from pathlib import Path

from alembic import command
from alembic.config import Config
from sqlalchemy import Boolean, Date, DateTime, Float, ForeignKeyConstraint, Integer, MetaData, String, Text, UniqueConstraint, create_engine, inspect
from sqlalchemy.types import TypeDecorator

from app.models import Base

API_ROOT = Path(__file__).resolve().parents[1]


def _type_family(column_type) -> str:
    if isinstance(column_type, TypeDecorator):
        column_type = column_type.impl
    if isinstance(column_type, Boolean):
        return "boolean"
    if isinstance(column_type, Integer):
        return "integer"
    if isinstance(column_type, Float):
        return "float"
    if isinstance(column_type, DateTime):
        return "datetime"
    if isinstance(column_type, Date):
        return "date"
    if isinstance(column_type, Text):
        return "text"
    if isinstance(column_type, String):
        return "string"
    return column_type.__class__.__name__.lower()


def _expected_indexes(table) -> set[tuple[str, tuple[str, ...], bool]]:
    return {
        (index.name, tuple(column.name for column in index.columns), bool(index.unique))
        for index in table.indexes
    }


def _actual_indexes(inspector, table_name: str) -> set[tuple[str, tuple[str, ...], bool]]:
    return {
        (index["name"], tuple(index["column_names"]), bool(index.get("unique")))
        for index in inspector.get_indexes(table_name)
    }


def _expected_unique_constraints(table) -> set[tuple[str, ...]]:
    return {
        tuple(column.name for column in constraint.columns)
        for constraint in table.constraints
        if isinstance(constraint, UniqueConstraint)
    }


def _actual_unique_constraints(inspector, table_name: str) -> set[tuple[str, ...]]:
    return {
        tuple(constraint["column_names"])
        for constraint in inspector.get_unique_constraints(table_name)
    }


def _expected_foreign_keys(table) -> set[tuple[tuple[str, ...], str, tuple[str, ...]]]:
    return {
        (
            tuple(element.parent.name for element in constraint.elements),
            constraint.referred_table.name,
            tuple(element.column.name for element in constraint.elements),
        )
        for constraint in table.constraints
        if isinstance(constraint, ForeignKeyConstraint)
    }


def _actual_foreign_keys(inspector, table_name: str) -> set[tuple[tuple[str, ...], str, tuple[str, ...]]]:
    return {
        (
            tuple(foreign_key["constrained_columns"]),
            foreign_key["referred_table"],
            tuple(foreign_key["referred_columns"]),
        )
        for foreign_key in inspector.get_foreign_keys(table_name)
    }


def test_sqlite_alembic_schema_matches_phase1_metadata():
    temp = tempfile.NamedTemporaryFile(delete=False, suffix=".db")
    temp.close()
    db_path = Path(temp.name)
    db_path.unlink(missing_ok=True)
    database_url = f"sqlite:///{db_path.as_posix()}"

    alembic_cfg = Config(str(API_ROOT / "alembic.ini"))
    alembic_cfg.set_main_option("script_location", str(API_ROOT / "migrations"))
    alembic_cfg.set_main_option("sqlalchemy.url", database_url)
    command.upgrade(alembic_cfg, "head")

    engine = create_engine(database_url, future=True)
    try:
        reflected = MetaData()
        reflected.reflect(engine)
        inspector = inspect(engine)

        actual_tables = set(reflected.tables) - {"alembic_version"}
        expected_tables = set(Base.metadata.tables)
        assert actual_tables == expected_tables

        for table_name in sorted(expected_tables):
            expected_table = Base.metadata.tables[table_name]
            actual_table = reflected.tables[table_name]
            assert set(actual_table.columns.keys()) == set(expected_table.columns.keys())

            for column_name, expected_column in expected_table.columns.items():
                actual_column = actual_table.columns[column_name]
                assert actual_column.primary_key == expected_column.primary_key, f"{table_name}.{column_name} primary_key drift"
                if not expected_column.primary_key:
                    assert actual_column.nullable == expected_column.nullable, f"{table_name}.{column_name} nullable drift"
                assert _type_family(actual_column.type) == _type_family(expected_column.type), f"{table_name}.{column_name} type drift"

            assert _actual_indexes(inspector, table_name) == _expected_indexes(expected_table), f"{table_name} index drift"
            assert _actual_unique_constraints(inspector, table_name) == _expected_unique_constraints(expected_table), f"{table_name} unique constraint drift"
            assert _actual_foreign_keys(inspector, table_name) == _expected_foreign_keys(expected_table), f"{table_name} foreign-key drift"
    finally:
        engine.dispose()
        db_path.unlink(missing_ok=True)
