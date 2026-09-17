from __future__ import annotations

import asyncio
import os
from logging.config import fileConfig

from alembic import context
from sqlalchemy import pool
from sqlalchemy.engine import Connection, make_url
from sqlalchemy.exc import ArgumentError
from sqlalchemy.ext.asyncio import AsyncEngine, async_engine_from_config

from app import models as _models  # noqa: F401
from app.core.database import Base

config = context.config

if config.config_file_name is not None:
    fileConfig(config.config_file_name)

target_metadata = Base.metadata


def migration_database_url() -> str:
    database_url = os.environ.get("MIGRATION_DATABASE_URL", "").strip()
    if not database_url:
        raise RuntimeError("MIGRATION_DATABASE_URL is required")

    try:
        driver_name = make_url(database_url).drivername
    except ArgumentError as error:
        raise RuntimeError("MIGRATION_DATABASE_URL must use postgresql+asyncpg") from error

    if driver_name != "postgresql+asyncpg":
        raise RuntimeError("MIGRATION_DATABASE_URL must use postgresql+asyncpg")
    return database_url


def context_options() -> dict[str, object]:
    return {
        "target_metadata": target_metadata,
        "include_schemas": True,
        "compare_type": True,
        "version_table_schema": "app",
    }


def run_migrations_offline() -> None:
    context.configure(
        url=migration_database_url(),
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
        **context_options(),
    )

    with context.begin_transaction():
        context.run_migrations()


def run_sync_migrations(connection: Connection) -> None:
    context.configure(connection=connection, **context_options())
    with context.begin_transaction():
        context.run_migrations()


async def run_async_migrations() -> None:
    configuration = config.get_section(config.config_ini_section, {})
    configuration["sqlalchemy.url"] = migration_database_url()
    connectable: AsyncEngine = async_engine_from_config(
        configuration,
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )

    try:
        async with connectable.connect() as connection:
            await connection.run_sync(run_sync_migrations)
    finally:
        await connectable.dispose()


if context.is_offline_mode():
    run_migrations_offline()
else:
    asyncio.run(run_async_migrations())
