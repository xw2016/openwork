"""
权限中间件
自动检查路由权限，基于路由上的 permission 注解判断当前用户是否有权访问

路由通过 endpoint 函数的 __permission__ 属性声明所需权限：
    @router.get("/tasks")
    async def list_tasks():
        ...
    list_tasks.__permission__ = Perm.MARKET_TASKS_LIST

未设置 __permission__ 的路由不进行权限检查（公开路由或已由其他机制保护）

当请求未携带 Authorization header 时，中间件放行请求，
由路由自身的依赖注入（如 get_current_user）决定是否要求认证。
"""

from __future__ import annotations

import re
from typing import Callable, Optional, Set

import structlog
from fastapi import Request, Response
from fastapi.responses import JSONResponse
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.routing import Match

from app.core.security import decode_token
from app.models.user import UserType

logger = structlog.get_logger("middleware.permission")


# 不需要权限检查的路径前缀（公开接口）
_PUBLIC_PATH_PREFIXES: Set[str] = {
    "/health",
    "/docs",
    "/openapi.json",
    "/redoc",
}


class PermissionMiddleware(BaseHTTPMiddleware):
    """
    权限检查中间件

    工作流程：
    1. 跳过公开路径和 OPTIONS 请求
    2. 匹配请求到 FastAPI 路由
    3. 检查路由 endpoint 是否设置了 __permission__ 属性
    4. 如果设置了，尝试从 JWT 中解析用户角色并校验权限
    5. 未携带 token 的请求放行（由路由级依赖处理认证）
    6. 携带 token 但权限不足的请求返回 403
    """

    async def dispatch(self, request: Request, call_next: Callable) -> Response:
        path = request.url.path
        method = request.method

        # 跳过 OPTIONS 预检请求
        if method == "OPTIONS":
            return await call_next(request)

        # 跳过公开路径
        for prefix in _PUBLIC_PATH_PREFIXES:
            if path == prefix or path.startswith(prefix + "/"):
                return await call_next(request)

        # 匹配路由，获取 endpoint 函数
        endpoint = self._resolve_endpoint(request)
        if endpoint is None:
            # 未匹配到路由，交给后续处理（404 等）
            return await call_next(request)

        # 检查 endpoint 是否声明了权限要求
        required_permission: Optional[str] = getattr(
            endpoint, "__permission__", None
        )
        if required_permission is None:
            # 无权限要求，放行
            return await call_next(request)

        # 未携带 Authorization header 时放行，
        # 由路由自身的依赖注入处理认证
        auth_header = request.headers.get("authorization")
        if not auth_header or not auth_header.startswith("Bearer "):
            return await call_next(request)

        # 从 JWT 解析用户角色
        user_type = await self._extract_user_type(request)
        if user_type is None:
            # token 无效或不含 role claim，放行
            # （由路由级 get_current_user 依赖做完整校验）
            return await call_next(request)

        # 管理员拥有全部权限，直接放行
        if user_type == UserType.ADMIN:
            return await call_next(request)

        # 检查权限
        from app.core.permissions import has_permission

        if not has_permission(user_type, required_permission):
            logger.warning(
                "permission_denied",
                user_type=user_type.value,
                required=required_permission,
                path=path,
                method=method,
            )
            return JSONResponse(
                status_code=403,
                content={
                    "code": 403,
                    "message": f"权限不足，需要权限: {required_permission}",
                    "data": None,
                },
            )

        return await call_next(request)

    @staticmethod
    def _resolve_endpoint(request: Request) -> Optional[Callable]:
        """从请求中匹配到 FastAPI 路由的 endpoint 函数"""
        for route in request.app.routes:
            match, _ = route.matches(request.scope)
            if match == Match.FULL:
                # FastAPI 的 APIRoute 有 endpoint 属性
                endpoint = getattr(route, "endpoint", None)
                if endpoint is not None:
                    return endpoint
        return None

    @staticmethod
    async def _extract_user_type(request: Request) -> Optional[UserType]:
        """
        从请求 Authorization header 解析 JWT，提取用户角色

        如果 JWT 中包含 role claim，直接使用。
        否则返回 None，由路由级依赖处理。
        """
        auth_header = request.headers.get("authorization")
        if not auth_header or not auth_header.startswith("Bearer "):
            return None

        token = auth_header[7:]
        try:
            payload = decode_token(token)
            token_type = payload.get("type")
            if token_type != "access":
                return None
            # 如果 JWT 中包含 role claim，直接使用
            role = payload.get("role")
            if role:
                try:
                    return UserType(role)
                except ValueError:
                    return None
            # 无 role claim 时返回 None，由路由级依赖处理
            return None
        except Exception:
            return None
