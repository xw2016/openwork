"""
认证路由
POST /v1/auth/register       - 手机号注册（也支持邮箱）
POST /v1/auth/register-email - 邮箱注册
POST /v1/auth/login          - 手机号/邮箱 + 密码登录
POST /v1/auth/refresh        - 刷新令牌
GET  /v1/auth/me             - 获取当前用户信息
GET  /v1/auth/permissions    - 获取当前用户权限列表
"""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Request, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.deps import get_current_user, get_db
from app.core.permissions import Perm, get_permissions_for_user_type
from app.core.security import create_access_token, create_refresh_token
from app.models.user import User
from app.modules.auth.login_guard import login_guard
from app.modules.auth.service import (
    authenticate_user,
    refresh_access_token,
    register_user,
    register_user_by_email,
)
from app.schemas.common import ResponseBase
from app.schemas.user import (
    LoginLogResponse,
    RefreshTokenRequest,
    TokenResponse,
    UserEmailRegisterRequest,
    UserInfoResponse,
    UserLoginRequest,
    UserRegisterRequest,
)
from app.utils.logger import get_logger

logger = get_logger(__name__)

router = APIRouter(prefix="/v1/auth", tags=["认证"])


def _get_client_ip(request: Request) -> str:
    """获取客户端真实 IP"""
    forwarded = request.headers.get("X-Forwarded-For")
    if forwarded:
        return forwarded.split(",")[0].strip()
    real_ip = request.headers.get("X-Real-IP")
    if real_ip:
        return real_ip
    if request.client:
        return request.client.host
    return "unknown"


def _get_user_agent(request: Request) -> str:
    """获取客户端设备信息"""
    return request.headers.get("User-Agent", "unknown")


@router.post(
    "/register",
    response_model=ResponseBase[UserInfoResponse],
    status_code=status.HTTP_201_CREATED,
    summary="用户注册",
)
async def register(
    body: UserRegisterRequest,
    db: Annotated[AsyncSession, Depends(get_db)],
):
    """
    用户注册（支持手机号和邮箱）
    - phone 和 email 至少提供一个
    - 提供手机号时进行格式校验
    - 密码需满足强度要求
    """
    try:
        user = await register_user(db, body)
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=str(e),
        )
    return ResponseBase(
        code=201,
        message="注册成功",
        data=UserInfoResponse.model_validate(user),
    )
register.__permission__ = Perm.AUTH_REGISTER


@router.post(
    "/register-email",
    response_model=ResponseBase[UserInfoResponse],
    status_code=status.HTTP_201_CREATED,
    summary="邮箱注册",
)
async def register_email(
    body: UserEmailRegisterRequest,
    db: Annotated[AsyncSession, Depends(get_db)],
):
    """
    邮箱注册新用户（独立端点）
    - 必须提供有效邮箱
    - 密码需满足强度要求
    """
    try:
        user = await register_user_by_email(db, body)
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=str(e),
        )
    return ResponseBase(
        code=201,
        message="注册成功",
        data=UserInfoResponse.model_validate(user),
    )
register_email.__permission__ = Perm.AUTH_REGISTER


@router.post(
    "/login",
    response_model=ResponseBase[TokenResponse],
    summary="用户登录",
)
async def login(
    body: UserLoginRequest,
    request: Request,
    db: Annotated[AsyncSession, Depends(get_db)],
):
    """
    用户登录（支持手机号或邮箱 + 密码）
    - 同一手机号/邮箱5次失败后锁定15分钟
    - 记录登录日志（IP、设备信息、时间）
    """
    ip = _get_client_ip(request)
    user_agent = _get_user_agent(request)

    try:
        user = await authenticate_user(db, body, ip=ip, user_agent=user_agent)
    except ValueError as e:
        # 账户被锁定
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail=str(e),
        )

    if user is None:
        # 获取剩余尝试次数
        remaining = login_guard.get_remaining_attempts(
            phone=body.phone, email=body.email
        )
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=f"手机号或密码错误（剩余 {remaining} 次尝试机会）",
        )

    access_token = create_access_token(data={"sub": str(user.id)})
    refresh_token = create_refresh_token(data={"sub": str(user.id)})

    return ResponseBase(
        message="登录成功",
        data=TokenResponse(
            access_token=access_token,
            refresh_token=refresh_token,
            token_type="bearer",
            expires_in=settings.ACCESS_TOKEN_EXPIRE_MINUTES * 60,
        ),
    )
login.__permission__ = Perm.AUTH_LOGIN


@router.post(
    "/refresh",
    response_model=ResponseBase[TokenResponse],
    summary="刷新令牌",
)
async def refresh_token(
    body: RefreshTokenRequest,
    db: Annotated[AsyncSession, Depends(get_db)],
):
    """使用 refresh token 获取新的 access token"""
    result = await refresh_access_token(db, body.refresh_token)
    if result is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="无效的刷新令牌",
        )
    return ResponseBase(
        message="令牌刷新成功",
        data=TokenResponse(
            access_token=result["access_token"],
            refresh_token=result["refresh_token"],
            token_type=result["token_type"],
            expires_in=settings.ACCESS_TOKEN_EXPIRE_MINUTES * 60,
        ),
    )
refresh_token.__permission__ = Perm.AUTH_REFRESH


@router.get(
    "/me",
    response_model=ResponseBase[UserInfoResponse],
    summary="获取当前用户信息",
)
async def get_me(
    current_user: Annotated[User, Depends(get_current_user)],
):
    """获取当前登录用户的信息"""
    return ResponseBase(
        data=UserInfoResponse.model_validate(current_user),
    )
get_me.__permission__ = Perm.AUTH_ME


@router.get(
    "/permissions",
    response_model=ResponseBase[list],
    summary="获取当前用户权限列表",
)
async def get_permissions(
    current_user: Annotated[User, Depends(get_current_user)],
):
    """获取当前登录用户的权限列表"""
    permissions = get_permissions_for_user_type(current_user.user_type)
    return ResponseBase(
        data=permissions,
    )
get_permissions.__permission__ = Perm.AUTH_PERMISSIONS


@router.get(
    "/login-logs",
    response_model=ResponseBase[list[LoginLogResponse]],
    summary="获取登录日志",
)
async def get_login_logs(
    current_user: Annotated[User, Depends(get_current_user)],
    limit: int = 50,
):
    """
    获取最近的登录日志
    需要登录后访问
    """
    logs = login_guard.get_login_logs(limit=limit)
    return ResponseBase(
        data=[LoginLogResponse(**log) for log in logs],
    )
get_login_logs.__permission__ = Perm.AUTH_ME
