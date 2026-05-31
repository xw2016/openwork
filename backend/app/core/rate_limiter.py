"""
基于 Redis 的滑动窗口限流器
- 支持按 IP、按用户、按接口粒度限流
- 装饰器形式方便使用：@rate_limit(times=5, seconds=60)
- 无 Redis 时自动降级到内存限流
"""

from __future__ import annotations

import time
import functools
from collections import OrderedDict
from typing import Callable, Optional

import structlog
from fastapi import HTTPException, Request, status

logger = structlog.get_logger("core.rate_limiter")

# ============================================================
# 内存降级存储
# ============================================================

class BoundedMemoryStore:
    """Memory store with max 10000 keys and LRU eviction to prevent unbounded growth."""

    def __init__(self, max_keys: int = 10000):
        self._store: OrderedDict[str, list[float]] = OrderedDict()
        self._max_keys = max_keys

    def get(self, key: str) -> list[float]:
        return self._store.get(key, [])

    def set(self, key: str, value: list[float]) -> None:
        if key not in self._store and len(self._store) >= self._max_keys:
            self._store.popitem(last=False)  # Remove oldest
        self._store[key] = value

    def __contains__(self, key: str) -> bool:
        return key in self._store

    def __getitem__(self, key: str) -> list[float]:
        return self._store[key]

    def __setitem__(self, key: str, value: list[float]) -> None:
        self.set(key, value)


_memory_store = BoundedMemoryStore()


def _cleanup_memory_key(key: str, window: float) -> int:
    """清理内存中过期的记录，返回剩余数量"""
    now = time.time()
    if key in _memory_store:
        _memory_store[key] = [t for t in _memory_store[key] if t > now - window]
    else:
        _memory_store[key] = []
    return len(_memory_store[key])


# ============================================================
# 滑动窗口限流核心
# ============================================================

async def check_rate_limit(
    key: str,
    max_requests: int,
    window_seconds: int,
    redis_client=None,
) -> tuple[bool, int, int]:
    """
    检查限流
    :param key: 限流键（如 "rate:ip:127.0.0.1"）
    :param max_requests: 窗口内最大请求数
    :param window_seconds: 时间窗口（秒）
    :param redis_client: Redis 客户端实例（可选）
    :return: (是否允许, 当前计数, 剩余次数)
    """
    now = time.time()
    window_start = now - window_seconds

    # 尝试 Redis
    if redis_client is not None:
        try:
            pipe = redis_client.pipeline()
            pipe.zremrangebyscore(key, 0, window_start)
            pipe.zadd(key, {str(now): now})
            pipe.zcard(key)
            pipe.expire(key, window_seconds)
            results = await pipe.execute()

            current = results[2]
            remaining = max(0, max_requests - current)
            return current <= max_requests, current, remaining
        except Exception as e:
            logger.warning("rate_limit_redis_error", error=str(e), key=key)
            # 降级到内存

    # 内存限流
    count = _cleanup_memory_key(key, window_seconds)
    count += 1
    _memory_store[key].append(now)
    remaining = max(0, max_requests - count)
    return count <= max_requests, count, remaining


def _get_client_ip(request: Request, trusted_proxies: Optional[set[str]] = None) -> str:
    """获取客户端真实 IP，仅信任已知代理的转发头"""
    client_host = request.client.host if request.client else "unknown"

    # Only trust proxy headers if we know the direct connection is from a trusted proxy
    if trusted_proxies and client_host in trusted_proxies:
        forwarded = request.headers.get("X-Forwarded-For")
        if forwarded:
            return forwarded.split(",")[0].strip()
        real_ip = request.headers.get("X-Real-IP")
        if real_ip:
            return real_ip

    return client_host


# ============================================================
# 装饰器限流
# ============================================================

def rate_limit(
    times: int = 60,
    seconds: int = 60,
    key_func: Optional[Callable[[Request], str]] = None,
    message: str = "请求过于频繁，请稍后再试",
):
    """
    路由限流装饰器

    用法：
        @router.post("/login")
        @rate_limit(times=5, seconds=60, message="登录尝试过多")
        async def login(request: Request, ...):
            ...

    :param times: 时间窗口内允许的最大请求数
    :param seconds: 时间窗口秒数
    :param key_func: 自定义限流键函数（默认按 IP）
    :param message: 超限时返回的错误消息
    """

    def decorator(func: Callable) -> Callable:
        @functools.wraps(func)
        async def wrapper(*args, **kwargs):
            # 从函数参数中提取 Request 对象
            request: Optional[Request] = kwargs.get("request")
            if request is None:
                for arg in args:
                    if isinstance(arg, Request):
                        request = arg
                        break

            if request is None:
                # 没有 Request 对象时直接放行
                return await func(*args, **kwargs)

            # 获取 Redis 客户端（通过 app.state）
            redis_client = None
            try:
                redis_client = request.app.state.redis
            except AttributeError:
                pass

            # 构建限流键
            if key_func:
                client_id = key_func(request)
            else:
                client_id = _get_client_ip(request)

            path = request.url.path
            rate_key = f"rate:decorator:{path}:{client_id}"

            allowed, count, remaining = await check_rate_limit(
                rate_key, times, seconds, redis_client
            )

            if not allowed:
                logger.warning(
                    "decorator_rate_limit_exceeded",
                    key=rate_key,
                    count=count,
                    limit=times,
                    path=path,
                )
                raise HTTPException(
                    status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                    detail=message,
                )

            return await func(*args, **kwargs)

        return wrapper

    return decorator


# ============================================================
# 用户级限流（基于 JWT 中的 user_id）
# ============================================================

def rate_limit_by_user(
    times: int = 100,
    seconds: int = 60,
    message: str = "操作过于频繁，请稍后再试",
):
    """
    按登录用户限流的装饰器
    需要路由使用了 get_current_user 依赖

    用法：
        @router.post("/submit")
        @rate_limit_by_user(times=10, seconds=60)
        async def submit(current_user: User = Depends(get_current_user)):
            ...
    """

    def user_key_func(request: Request) -> str:
        # 尝试从已解析的 token 中获取用户 ID
        try:
            auth = request.headers.get("Authorization", "")
            if auth.startswith("Bearer "):
                from app.core.security import decode_token
                payload = decode_token(auth[7:])
                user_id = payload.get("sub", "anonymous")
                return f"user:{user_id}"
        except Exception:
            pass
        # 降级到 IP
        return f"ip:{_get_client_ip(request)}"

    return rate_limit(times=times, seconds=seconds, key_func=user_key_func, message=message)
