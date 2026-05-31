"""
认证业务逻辑
处理注册、登录、刷新令牌等业务
"""

from __future__ import annotations

from typing import Optional
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.security import (
    create_access_token,
    create_refresh_token,
    decode_token,
    hash_password,
    verify_password,
)
from app.models.user import User, UserStatus, UserType
from app.schemas.user import UserLoginRequest, UserRegisterRequest
from app.utils.logger import get_logger

logger = get_logger(__name__)


async def register_user(db: AsyncSession, data: UserRegisterRequest) -> User:
    """
    用户注册（手机号注册）
    :raises ValueError: 手机号已存在
    """
    # 检查手机号是否已注册
    existing = await db.execute(select(User).where(User.phone == data.phone))
    if existing.scalar_one_or_none() is not None:
        raise ValueError("该手机号已注册")

    # 创建用户
    user = User(
        phone=data.phone,
        nickname=data.nickname,
        user_type=data.user_type,
        hashed_password=hash_password(data.password),
        status=UserStatus.ACTIVE,
    )
    db.add(user)
    await db.commit()
    await db.refresh(user)

    logger.info("user_registered", user_id=str(user.id), phone=data.phone)
    return user


async def authenticate_user(db: AsyncSession, data: UserLoginRequest) -> Optional[User]:
    """
    用户认证（手机号 + 密码登录）
    :return: 认证成功返回 User，失败返回 None
    """
    result = await db.execute(select(User).where(User.phone == data.phone))
    user = result.scalar_one_or_none()
    if user is None:
        return None
    if not verify_password(data.password, user.hashed_password):
        return None
    if user.status != UserStatus.ACTIVE:
        return None
    return user


async def get_user_by_id(db: AsyncSession, user_id: UUID) -> Optional[User]:
    """根据 ID 获取用户"""
    result = await db.execute(select(User).where(User.id == user_id))
    return result.scalar_one_or_none()


async def refresh_access_token(db: AsyncSession, refresh_token_str: str) -> Optional[dict]:
    """
    使用 refresh token 获取新的 access token
    :return: 包含新 token 信息的字典，失败返回 None
    """
    try:
        payload = decode_token(refresh_token_str)
        if payload.get("type") != "refresh":
            return None
        user_id = payload.get("sub")
        if user_id is None:
            return None
    except Exception:
        return None

    user = await get_user_by_id(db, UUID(user_id))
    if user is None or user.status != UserStatus.ACTIVE:
        return None

    new_access = create_access_token(data={"sub": str(user.id)})
    new_refresh = create_refresh_token(data={"sub": str(user.id)})

    return {
        "access_token": new_access,
        "refresh_token": new_refresh,
        "token_type": "bearer",
    }
