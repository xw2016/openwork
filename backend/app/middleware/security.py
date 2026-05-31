"""
安全中间件
- RateLimiter: 基于 Redis 的令牌桶限流
- SecurityHeaders: 安全响应头
- RequestSizeLimit: 请求体大小限制
"""

from __future__ import annotations

import time
from typing import Callable, Optional

import structlog
from fastapi import Request, Response
from fastapi.responses import JSONResponse
from starlette.middleware.base import BaseHTTPMiddleware

logger = structlog.get_logger("middleware.security")


# ============================================================
# 安全响应头中间件
# ============================================================

class SecurityHeadersMiddleware(BaseHTTPMiddleware):
    """
    为所有响应添加安全头：
    - X-Content-Type-Options: nosniff（防止 MIME 类型嗅探）
    - X-Frame-Options: DENY（禁止 iframe 嵌入）
    - X-XSS-Protection: 1; mode=block（浏览器 XSS 过滤）
    - Strict-Transport-Security: 强制 HTTPS
    - Content-Security-Policy: 限制资源加载来源
    - Referrer-Policy: 控制 Referer 头信息
    - Permissions-Policy: 限制浏览器 API 权限
    """

    async def dispatch(self, request: Request, call_next: Callable) -> Response:
        response = await call_next(request)
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["X-Frame-Options"] = "DENY"
        response.headers["X-XSS-Protection"] = "1; mode=block"
        response.headers["Strict-Transport-Security"] = (
            "max-age=31536000; includeSubDomains"
        )
        response.headers["Content-Security-Policy"] = (
            "default-src 'self'; "
            "script-src 'self'; "
            "style-src 'self' 'unsafe-inline'; "
            "img-src 'self' data: https:; "
            "connect-src 'self'"
        )
        response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
        response.headers["Permissions-Policy"] = (
            "camera=(), microphone=(), geolocation=()"
        )
        # 移除服务器指纹头（如果存在）
        response.headers.pop("server", None)
        response.headers.pop("X-Powered-By", None)
        return response


# ============================================================
# 请求体大小限制中间件
# ============================================================

class RequestSizeLimitMiddleware(BaseHTTPMiddleware):
    """
    限制请求体大小，防止恶意大文件上传攻击
    默认限制 10MB
    """

    def __init__(self, app, max_size_mb: int = 10):
        super().__init__(app)
        self.max_size_bytes = max_size_mb * 1024 * 1024

    async def dispatch(self, request: Request, call_next: Callable) -> Response:
        # 检查 Content-Length header
        content_length = request.headers.get("content-length")
        if content_length:
            try:
                if int(content_length) > self.max_size_bytes:
                    logger.warning(
                        "request_too_large",
                        content_length=content_length,
                        max_size=self.max_size_bytes,
                        path=request.url.path,
                        client=request.client.host if request.client else "unknown",
                    )
                    return JSONResponse(
                        status_code=413,
                        content={
                            "code": 413,
                            "message": f"请求体过大，最大允许 {self.max_size_bytes // (1024 * 1024)}MB",
                            "data": None,
                        },
                    )
            except ValueError:
                pass

        return await call_next(request)


# ============================================================
# 基于 Redis 的令牌桶限流中间件
# ============================================================

class RateLimiterMiddleware(BaseHTTPMiddleware):
    """
    基于 Redis 滑动窗口的 IP 限流中间件
    - 通用接口：每 IP 每分钟 60 次
    - 登录接口：每 IP 每分钟 5 次
    - 无 Redis 时降级放行（可用内存字典做简单限流）
    """

    def __init__(
        self,
        app,
        redis_url: Optional[str] = None,
        default_limit: int = 60,
        login_limit: int = 5,
        window_seconds: int = 60,
    ):
        super().__init__(app)
        self.redis_url = redis_url
        self.default_limit = default_limit
        self.login_limit = login_limit
        self.window_seconds = window_seconds
        self._redis = None
        # 内存降级方案
        self._memory_store: dict[str, list[float]] = {}

        # 登录路径列表
        self._login_paths = {"/api/v1/auth/login", "/api/v1/auth/register"}

    async def _get_redis(self):
        """延迟初始化 Redis 连接"""
        if self._redis is None and self.redis_url:
            try:
                import redis.asyncio as aioredis
                self._redis = aioredis.from_url(
                    self.redis_url,
                    encoding="utf-8",
                    decode_responses=True,
                )
                # 验证连接
                await self._redis.ping()
                logger.info("rate_limiter_redis_connected", url=self.redis_url)
            except Exception as e:
                logger.warning("rate_limiter_redis_failed", error=str(e))
                self._redis = False  # 标记为不可用，不再重试
        return self._redis if self._redis and self._redis is not False else None

    def _get_client_ip(self, request: Request) -> str:
        """获取客户端真实 IP（支持反向代理）"""
        # 优先从 X-Forwarded-For 取（反向代理场景）
        forwarded_for = request.headers.get("X-Forwarded-For")
        if forwarded_for:
            return forwarded_for.split(",")[0].strip()
        # 其次从 X-Real-IP 取
        real_ip = request.headers.get("X-Real-IP")
        if real_ip:
            return real_ip
        # 最后用直连 IP
        if request.client:
            return request.client.host
        return "unknown"

    async def _check_rate_redis(self, key: str, limit: int) -> tuple[bool, int, int]:
        """
        使用 Redis 滑动窗口限流
        返回: (是否允许, 当前计数, 剩余次数)
        """
        redis = await self._get_redis()
        if redis is None:
            return True, 0, limit  # Redis 不可用时放行

        now = time.time()
        window_start = now - self.window_seconds

        try:
            pipe = redis.pipeline()
            # 移除窗口外的记录
            pipe.zremrangebyscore(key, 0, window_start)
            # 添加当前请求
            pipe.zadd(key, {str(now): now})
            # 统计窗口内请求数
            pipe.zcard(key)
            # 设置 key 过期（自动清理）
            pipe.expire(key, self.window_seconds)
            results = await pipe.execute()

            current_count = results[2]
            remaining = max(0, limit - current_count)
            allowed = current_count <= limit

            return allowed, current_count, remaining
        except Exception as e:
            logger.error("rate_limit_redis_error", error=str(e))
            return True, 0, limit  # Redis 出错时放行

    async def _check_rate_memory(self, key: str, limit: int) -> tuple[bool, int, int]:
        """内存降级限流方案"""
        now = time.time()
        window_start = now - self.window_seconds

        if key not in self._memory_store:
            self._memory_store[key] = []

        # 清理窗口外记录
        self._memory_store[key] = [
            t for t in self._memory_store[key] if t > window_start
        ]
        self._memory_store[key].append(now)

        current_count = len(self._memory_store[key])
        remaining = max(0, limit - current_count)
        return current_count <= limit, current_count, remaining

    async def _check_rate(self, key: str, limit: int) -> tuple[bool, int, int]:
        """检查限流，优先用 Redis，失败时降级到内存"""
        allowed, count, remaining = await self._check_rate_redis(key, limit)
        if not allowed or count > 0:
            return allowed, count, remaining
        return await self._check_rate_memory(key, limit)

    async def dispatch(self, request: Request, call_next: Callable) -> Response:
        client_ip = self._get_client_ip(request)
        path = request.url.path

        # 判断限流级别
        is_login = path in self._login_paths
        limit = self.login_limit if is_login else self.default_limit
        prefix = "login" if is_login else "general"
        rate_key = f"rate:{prefix}:{client_ip}"

        allowed, count, remaining = await self._check_rate(rate_key, limit)

        if not allowed:
            logger.warning(
                "rate_limit_exceeded",
                client_ip=client_ip,
                path=path,
                count=count,
                limit=limit,
            )
            return JSONResponse(
                status_code=429,
                content={
                    "code": 429,
                    "message": "请求过于频繁，请稍后再试",
                    "data": None,
                },
                headers={
                    "Retry-After": str(self.window_seconds),
                    "X-RateLimit-Limit": str(limit),
                    "X-RateLimit-Remaining": "0",
                    "X-RateLimit-Reset": str(int(time.time()) + self.window_seconds),
                },
            )

        response = await call_next(request)

        # 添加限流信息到响应头
        response.headers["X-RateLimit-Limit"] = str(limit)
        response.headers["X-RateLimit-Remaining"] = str(remaining)
        response.headers["X-RateLimit-Reset"] = str(
            int(time.time()) + self.window_seconds
        )

        return response
