"""
OpenWork 后端入口
FastAPI 应用，挂载路由、中间件、CORS
"""

from __future__ import annotations

import uuid
from contextlib import asynccontextmanager

import structlog
from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from app.core.config import settings
from app.core.exceptions import register_exception_handlers
from app.core.encryption import init_encryption
from app.middleware.security import (
    RateLimiterMiddleware,
    RequestSizeLimitMiddleware,
    SecurityHeadersMiddleware,
)
from app.utils.logger import setup_logging
from app.modules.auth.router import router as auth_router
from app.modules.intent.router import router as intent_router
from app.modules.contract.router import router as contract_router
from app.modules.market.router import router as market_router
from app.modules.acceptance.router import router as acceptance_router
from app.modules.payment.router import router as payment_router
from app.modules.credit.router import router as credit_router
from app.modules.blockchain.router import router as blockchain_router


@asynccontextmanager
async def lifespan(app: FastAPI):
    """应用生命周期管理"""
    setup_logging()
    logger = structlog.get_logger("app.startup")
    logger.info("app_starting", project=settings.PROJECT_NAME, version=settings.VERSION)

    # ---- 初始化加密模块 ----
    try:
        init_encryption(settings.AES_SECRET_KEY)
        logger.info("encryption_initialized")
    except Exception as e:
        logger.error("encryption_init_failed", error=str(e))

    # ---- 初始化 Redis 连接 ----
    redis_client = None
    try:
        import redis.asyncio as aioredis
        redis_client = aioredis.from_url(
            settings.REDIS_URL,
            encoding="utf-8",
            decode_responses=True,
        )
        await redis_client.ping()
        app.state.redis = redis_client
        logger.info("redis_connected", url=settings.REDIS_URL)
    except Exception as e:
        logger.warning("redis_connection_failed", error=str(e), fallback="memory_rate_limit")
        app.state.redis = None

    yield

    # ---- 关闭资源 ----
    if redis_client:
        try:
            await redis_client.close()
            logger.info("redis_disconnected")
        except Exception:
            pass

    logger.info("app_shutting_down")


def create_app() -> FastAPI:
    """创建并配置 FastAPI 应用实例"""

    app = FastAPI(
        title=settings.PROJECT_NAME,
        version=settings.VERSION,
        description="OpenWork 可信任务市场 API",
        lifespan=lifespan,
    )

    # ---- 安全中间件（按顺序添加，后添加的先执行） ----

    # 1. 请求体大小限制（最外层，尽早拦截大请求）
    app.add_middleware(
        RequestSizeLimitMiddleware,
        max_size_mb=settings.REQUEST_MAX_SIZE_MB,
    )

    # 2. IP 限流
    app.add_middleware(
        RateLimiterMiddleware,
        redis_url=settings.REDIS_URL,
        default_limit=settings.RATE_LIMIT_PER_MINUTE,
        login_limit=settings.RATE_LIMIT_LOGIN_PER_MINUTE,
    )

    # 3. 安全响应头
    app.add_middleware(SecurityHeadersMiddleware)

    # ---- CORS 中间件 ----
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.CORS_ORIGINS,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    # ---- 请求ID中间件 ----
    @app.middleware("http")
    async def request_id_middleware(request: Request, call_next):
        """为每个请求分配唯一 ID，注入到响应 header 和 structlog 上下文"""
        request_id = request.headers.get("X-Request-ID", str(uuid.uuid4()))
        structlog.contextvars.clear_contextvars()
        structlog.contextvars.bind_contextvars(request_id=request_id)

        response = await call_next(request)
        response.headers["X-Request-ID"] = request_id
        return response

    # ---- 注册全局异常处理器 ----
    register_exception_handlers(app)

    # ---- 健康检查 ----
    @app.get("/health", tags=["系统"])
    async def health_check():
        """健康检查端点"""
        return JSONResponse(
            content={
                "code": 200,
                "message": "ok",
                "data": {
                    "project": settings.PROJECT_NAME,
                    "version": settings.VERSION,
                },
            }
        )

    # ---- 注册业务路由 ----
    app.include_router(auth_router)
    app.include_router(intent_router)
    app.include_router(contract_router)
    app.include_router(market_router)
    app.include_router(acceptance_router)
    app.include_router(payment_router)
    app.include_router(credit_router)
    app.include_router(blockchain_router)

    return app


app = create_app()
