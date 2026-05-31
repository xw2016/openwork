"""
测试公共配置
提供测试用的数据库 session、应用客户端等 fixtures
使用 SQLite 内存数据库代替 PostgreSQL
"""

from __future__ import annotations

import asyncio
from typing import AsyncGenerator
from unittest.mock import AsyncMock, MagicMock

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy import event
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine, async_sessionmaker

from app.db.base import Base
from app.core.deps import get_db
from app.db.session import async_session_factory


# ============================================================
# 测试数据库配置（使用 SQLite 内存数据库）
# ============================================================

TEST_DATABASE_URL = "sqlite+aiosqlite:///:memory:"

test_engine = create_async_engine(
    TEST_DATABASE_URL,
    echo=False,
)

test_async_session_factory = async_sessionmaker(
    bind=test_engine,
    class_=AsyncSession,
    expire_on_commit=False,
)


# ============================================================
# SQLite JSONB 兼容处理
# ============================================================

from sqlalchemy.dialects.postgresql import JSONB as PG_JSONB
from sqlalchemy.ext.compiler import compiles


@compiles(PG_JSONB, "sqlite")
def _compile_jsonb_sqlite(type_, compiler, **kw):
    """将 JSONB 编译为 SQLite 兼容的 JSON 类型"""
    return "JSON"


# ============================================================
# Fixtures
# ============================================================

@pytest.fixture(scope="session")
def event_loop():
    """创建事件循环（整个测试会话共享）"""
    loop = asyncio.new_event_loop()
    yield loop
    loop.close()


@pytest_asyncio.fixture(autouse=True)
async def setup_database():
    """
    每个测试前创建表，测试后清理
    使用 SQLite 内存数据库
    """
    async with test_engine.begin() as conn:
        # 导入所有模型以确保表被创建
        import app.models.user  # noqa: F401
        import app.models.intent_blueprint  # noqa: F401
        await conn.run_sync(Base.metadata.create_all)
    yield
    async with test_engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)


@pytest_asyncio.fixture
async def db_session() -> AsyncGenerator[AsyncSession, None]:
    """提供测试用的数据库 session（SQLite 内存数据库）"""
    async with test_async_session_factory() as session:
        yield session
        await session.rollback()


@pytest_asyncio.fixture
async def client(db_session: AsyncSession) -> AsyncGenerator[AsyncClient, None]:
    """
    提供测试用的 HTTP 客户端
    覆盖数据库依赖为测试数据库，禁用中间件
    """
    from app.main import create_app
    app = create_app()

    # 覆盖数据库依赖，使用测试数据库
    async def override_get_db():
        yield db_session

    app.dependency_overrides[get_db] = override_get_db

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://testserver") as ac:
        yield ac

    app.dependency_overrides.clear()
