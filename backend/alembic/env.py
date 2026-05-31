"""
Alembic 迁移环境配置
"""

from logging.config import fileConfig

from alembic import context
from sqlalchemy import pool
from sqlalchemy.engine import Connection
from sqlalchemy import create_engine

# 导入所有 ORM 模型，确保 alembic 能检测到
from app.db.base import Base
import app.models  # noqa: F401

from app.core.config import settings

# Alembic Config 对象
config = context.config

# 配置日志
if config.config_file_name is not None:
    fileConfig(config.config_file_name)

# 设置 metadata，alembic 根据它自动生成迁移
target_metadata = Base.metadata

# 将 async URL 转为 sync URL（alembic 使用同步引擎）
SYNC_DATABASE_URL = settings.DATABASE_URL.replace("+asyncpg", "")


def run_migrations_offline() -> None:
    """以 'offline' 模式运行迁移（生成 SQL 脚本）"""
    url = SYNC_DATABASE_URL
    context.configure(
        url=url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
    )
    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    """以 'online' 模式运行迁移（直接连接数据库）"""
    connectable = create_engine(SYNC_DATABASE_URL, poolclass=pool.NullPool)
    with connectable.connect() as connection:
        context.configure(
            connection=connection,
            target_metadata=target_metadata,
        )
        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
