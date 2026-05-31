"""
认证路由
POST /v1/auth/register  - 手机号注册
POST /v1/auth/login     - 手机号 + 密码登录
POST /v1/auth/refresh   - 刷新令牌
GET  /v1/auth/me        - 获取当前用户信息
"""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.deps import get_current_user, get_db
from app.core.security import create_access_token, create_refresh_token
from app.models.user import User
from app.modules.auth.service import (
    authenticate_user,
    refresh_access_token,
    register_user,
)
from app.schemas.common import ResponseBase
from app.schemas.user import (
    RefreshTokenRequest,
    TokenResponse,
    UserInfoResponse,
    UserLoginRequest,
    UserRegisterRequest,
)

router = APIRouter(prefix="/v1/auth", tags=["认证"])


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
    """手机号注册新用户"""
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


@router.post(
    "/login",
    response_model=ResponseBase[TokenResponse],
    summary="用户登录",
)
async def login(
    body: UserLoginRequest,
    db: Annotated[AsyncSession, Depends(get_db)],
):
    """手机号 + 密码登录，返回 JWT 令牌"""
    user = await authenticate_user(db, body)
    if user is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="手机号或密码错误",
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
