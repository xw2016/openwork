"""
用户资料业务逻辑
处理资料查询、更新、头像上传、实名认证、统计等
"""

from __future__ import annotations

import base64
from datetime import datetime, timezone
from typing import Optional
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.encryption import encrypt_sensitive_field
from app.models.user import User, UserType
from app.schemas.user import (
    AvatarUploadRequest,
    ProfileUpdateRequest,
    VerifyRequest,
)
from app.utils.logger import get_logger

logger = get_logger(__name__)


async def get_user_by_id(db: AsyncSession, user_id: UUID) -> Optional[User]:
    """根据 ID 获取用户"""
    result = await db.execute(select(User).where(User.id == user_id))
    return result.scalar_one_or_none()


async def get_user_profile(db: AsyncSession, user_id: UUID) -> Optional[User]:
    """
    获取用户公开资料
    :return: User 对象，不存在返回 None
    """
    return await get_user_by_id(db, user_id)


async def update_profile(
    db: AsyncSession, user: User, data: ProfileUpdateRequest
) -> User:
    """
    更新当前用户资料
    只更新非 None 的字段
    """
    update_data = data.model_dump(exclude_unset=True)
    for field, value in update_data.items():
        if hasattr(user, field):
            setattr(user, field, value)

    await db.commit()
    await db.refresh(user)
    logger.info("profile_updated", user_id=str(user.id), fields=list(update_data.keys()))
    return user


async def upload_avatar(
    db: AsyncSession, user: User, data: AvatarUploadRequest
) -> User:
    """
    上传头像（支持 base64 或 URL）
    """
    if data.avatar_type == "url":
        user.avatar = data.avatar_data
    elif data.avatar_type == "base64":
        # 验证 base64 数据格式
        try:
            if "," in data.avatar_data:
                # 处理 data:image/xxx;base64,xxxx 格式
                header, encoded = data.avatar_data.split(",", 1)
                base64.b64decode(encoded)
            else:
                base64.b64decode(data.avatar_data)
            user.avatar = data.avatar_data
        except Exception as e:
            logger.warning("invalid_avatar_base64", user_id=str(user.id), error=str(e))
            raise ValueError("无效的 Base64 头像数据")

    await db.commit()
    await db.refresh(user)
    logger.info("avatar_uploaded", user_id=str(user.id))
    return user


async def verify_identity(
    db: AsyncSession, user: User, data: VerifyRequest
) -> User:
    """
    实名认证
    使用 AES 加密存储姓名和身份证号
    """
    # 检查是否已经实名认证
    if user.real_name is not None:
        raise ValueError("用户已完成实名认证，无需重复认证")

    # AES 加密存储敏感字段
    user.real_name = encrypt_sensitive_field(data.real_name)
    user.id_card = encrypt_sensitive_field(data.id_card)

    await db.commit()
    await db.refresh(user)
    logger.info("identity_verified", user_id=str(user.id))
    return user


async def get_user_stats(db: AsyncSession, user: User) -> dict:
    """
    获取用户统计信息
    当前返回基础统计，未来可扩展查询任务/接单表
    """
    return {
        "total_contracts": 0,
        "completed_contracts": 0,
        "total_earnings": 0.0,
        "average_rating": 0.0,
    }
