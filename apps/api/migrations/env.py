from __future__ import annotations

from logging.config import fileConfig

from alembic import context
from sqlalchemy import engine_from_config, pool

from app.core.config import get_settings
from app.models import Base  # noqa: F401
from app.models import auth  # noqa: F401
from app.models import finance  # noqa: F401
from app.models import plaid  # noqa: F401
from app.models import planning  # noqa: F401
from app.models import subscriptions  # noqa: F401

config = context.config
if config.config_file_name is not None:
    fileConfig(config.config_file_name)

# Honor an explicitly configured URL (tests, CI, or an ini/-x override); only fall
# back to app settings when none was provided. Overriding unconditionally would
# ignore a URL the caller deliberately set and, because get_settings() is cached,
# pin in-process migrations to whatever database was first configured.
_configured_url = config.get_main_option("sqlalchemy.url")
if not _configured_url:
    _configured_url = get_settings().database_url
config.set_main_option("sqlalchemy.url", _configured_url)
target_metadata = Base.metadata


def run_migrations_offline() -> None:
    url = config.get_main_option("sqlalchemy.url")
    context.configure(url=url, target_metadata=target_metadata, literal_binds=True, dialect_opts={"paramstyle": "named"})
    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    connectable = engine_from_config(
        config.get_section(config.config_ini_section, {}),
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )
    with connectable.connect() as connection:
        context.configure(connection=connection, target_metadata=target_metadata)
        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
