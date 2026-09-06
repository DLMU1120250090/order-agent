"""Alembic 迁移环境（order-agent，异步 aiomysql）。

- 数据库地址：环境变量 DATABASE_URL 优先，其次读取 order-agent/.env 的 DATABASE_URL；
- 元数据：SQLModel.metadata（import app.models.database 后注册全部 table=True 模型）。
"""
import asyncio
import os
import pathlib
from logging.config import fileConfig

from sqlalchemy import pool
from sqlalchemy.engine import Connection
from sqlalchemy.ext.asyncio import async_engine_from_config

from alembic import context

config = context.config

if config.config_file_name is not None:
    fileConfig(config.config_file_name)


def _database_url() -> str:
    """取 DATABASE_URL：环境变量优先，其次 order-agent/.env。"""
    env_url = os.environ.get("DATABASE_URL")
    if env_url:
        return env_url
    env_file = pathlib.Path(__file__).resolve().parent.parent / ".env"
    if env_file.exists():
        for raw in env_file.read_text(encoding="utf-8").splitlines():
            line = raw.strip()
            if line.startswith("DATABASE_URL="):
                return line.split("=", 1)[1].strip().strip('"').strip("'")
    raise RuntimeError("未找到 DATABASE_URL：请配置 order-agent/.env 或环境变量")


url = _database_url()

# SQLModel 元数据：先导入模型模块，让全部 table=True 类注册到 SQLModel.metadata
import app.models.database  # noqa: E402,F401
from sqlmodel import SQLModel  # noqa: E402

target_metadata = SQLModel.metadata


def run_migrations_offline() -> None:
    """Offline 模式：仅输出 SQL，不连库。"""
    context.configure(
        url=url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
    )

    with context.begin_transaction():
        context.run_migrations()


def do_run_migrations(connection: Connection) -> None:
    context.configure(connection=connection, target_metadata=target_metadata)

    with context.begin_transaction():
        context.run_migrations()


async def run_async_migrations() -> None:
    connectable = async_engine_from_config(
        config.get_section(config.config_ini_section, {}),
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
        url=url,
    )

    async with connectable.connect() as connection:
        await connection.run_sync(do_run_migrations)

    await connectable.dispose()


def run_migrations_online() -> None:
    asyncio.run(run_async_migrations())


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
