"""
认证业务逻辑
处理注册、登录、刷新令牌等业务
支持手机号注册和邮箱注册
"""

from __future__ import annotations

from typing import Optional
from uuid import UUID

from sqlalchemy import or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.security import (
    create_access_token,
    create_refresh_token,
    decode_token,
    hash_password,
    verify_password,
)
from app.models.user import User, UserStatus, UserType
from app.modules.auth.login_guard import login_guard
from app.schemas.user import (
    UserEmailRegisterRequest,
    UserLoginRequest,
    UserRegisterRequest,
)
from app.utils.logger import get_logger

logger = get_logger(__name__)


async def register_user(db: AsyncSession, data: UserRegisterRequest) -> User:
    """
    用户注册（支持手机号和邮箱注册）
    phone 和 email 至少需要提供一个
    :raises ValueError: 手机号或邮箱已存在、参数错误
    """
    # 校验：至少需要提供 phone 或 email
    if not data.phone and not data.email:
        raise ValueError("手机号和邮箱至少需要提供一个")

    # 检查手机号是否已注册（如果提供了手机号）
    if data.phone:
        existing_phone = await db.execute(
            select(User).where(User.phone == data.phone)
        )
        if existing_phone.scalar_one_or_none() is not None:
            raise ValueError("该手机号已注册")

    # 检查邮箱是否已注册（如果提供了邮箱）
    if data.email:
        existing_email = await db.execute(
            select(User).where(User.email == data.email)
        )
        if existing_email.scalar_one_or_none() is not None:
            raise ValueError("该邮箱已注册")

    # 创建用户
    user = User(
        phone=data.phone,
        email=data.email,
        nickname=data.nickname,
        user_type=data.user_type,
        hashed_password=hash_password(data.password),
        status=UserStatus.ACTIVE,
    )
    db.add(user)
    await db.commit()
    await db.refresh(user)

    logger.info(
        "user_registered",
        user_id=str(user.id),
        phone=data.phone,
        email=data.email,
        register_type="phone" if data.phone else "email",
    )
    return user


async def register_user_by_email(
    db: AsyncSession, data: UserEmailRegisterRequest
) -> User:
    """
    邮箱注册（独立端点）
    :raises ValueError: 邮箱已注册
    """
    # 检查邮箱是否已注册
    existing = await db.execute(
        select(User).where(User.email == data.email)
    )
    if existing.scalar_one_or_none() is not None:
        raise ValueError("该邮箱已注册")

    # 创建用户（邮箱注册，phone 为空）
    user = User(
        email=data.email,
        nickname=data.nickname,
        user_type=data.user_type,
        hashed_password=hash_password(data.password),
        status=UserStatus.ACTIVE,
    )
    db.add(user)
    await db.commit()
    await db.refresh(user)

    logger.info(
        "user_registered_by_email",
        user_id=str(user.id),
        email=data.email,
    )
    return user


async def authenticate_user(
    db: AsyncSession,
    data: UserLoginRequest,
    ip: str = "unknown",
    user_agent: str = "unknown",
) -> Optional[User]:
    """
    用户认证（支持手机号或邮箱 + 密码登录）
    包含登录失败次数限制和日志记录
    :return: 认证成功返回 User，失败返回 None
    :raises ValueError: 账户被锁定时抛出，附带剩余锁定时间
    """
    # 检查账户是否被锁定
    is_locked, remaining_seconds = login_guard.is_locked(
        phone=data.phone, email=data.email
    )
    if is_locked:
        raise ValueError(
            f"登录失败次数过多，账户已被锁定 {remaining_seconds} 秒后重试"
        )

    # 查询用户（支持手机号或邮箱）
    if data.phone:
        result = await db.execute(
            select(User).where(User.phone == data.phone)
        )
    elif data.email:
        result = await db.execute(
            select(User).where(User.email == data.email.lower())
        )
    else:
        # 记录失败
        login_guard.record_failure(
            phone=data.phone,
            email=data.email,
            ip=ip,
            user_agent=user_agent,
            failure_reason="未提供手机号或邮箱",
        )
        return None

    user = result.scalar_one_or_none()

    # 用户不存在
    if user is None:
        login_guard.record_failure(
            phone=data.phone,
            email=data.email,
            ip=ip,
            user_agent=user_agent,
            failure_reason="用户不存在",
        )
        return None

    # 密码错误
    if not verify_password(data.password, user.hashed_password):
        login_guard.record_failure(
            phone=data.phone,
            email=data.email,
            ip=ip,
            user_agent=user_agent,
            failure_reason="密码错误",
        )
        return None

    # 用户状态异常
    if user.status != UserStatus.ACTIVE:
        login_guard.record_failure(
            phone=data.phone,
            email=data.email,
            ip=ip,
            user_agent=user_agent,
            failure_reason=f"账户状态异常: {user.status.value}",
        )
        return None

    # 登录成功，记录并清除失败计数
    login_guard.record_success(
        user_id=str(user.id),
        phone=data.phone,
        email=data.email,
        ip=ip,
        user_agent=user_agent,
    )
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
