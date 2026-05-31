"""
用户资料路由
GET  /v1/users/{user_id}/profile - 获取用户公开资料
PUT  /v1/users/me/profile        - 更新当前用户资料
POST /v1/users/me/avatar         - 上传头像
POST /v1/users/me/verify         - 实名认证
GET  /v1/users/me/stats          - 获取用户统计
"""

from __future__ import annotations

from typing import Annotated
from uuid import UUID

import structlog
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.deps import OwnershipChecker, get_current_user, get_db
from app.models.user import User
from app.modules.profile.service import (
    get_user_profile,
    get_user_stats,
    update_profile,
    upload_avatar,
    verify_identity,
)
from app.schemas.common import ResponseBase
from app.schemas.user import (
    AvatarUploadRequest,
    ProfileResponse,
    ProfileUpdateRequest,
    UserStatsResponse,
    VerifyRequest,
)

logger = structlog.get_logger("modules.profile")

router = APIRouter(prefix="/v1/users", tags=["用户资料"])


@router.get(
    "/{user_id}/profile",
    response_model=ResponseBase[ProfileResponse],
    summary="获取用户公开资料",
)
async def get_profile(
    user_id: UUID,
    db: Annotated[AsyncSession, Depends(get_db)],
):
    """获取指定用户的公开资料（无需登录）"""
    user = await get_user_profile(db, user_id)
    if user is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="用户不存在",
        )
    return ResponseBase(
        data=ProfileResponse.model_validate(user),
    )


@router.put(
    "/me/profile",
    response_model=ResponseBase[ProfileResponse],
    summary="更新当前用户资料",
)
async def update_my_profile(
    body: ProfileUpdateRequest,
    db: Annotated[AsyncSession, Depends(get_db)],
    current_user: Annotated[User, Depends(get_current_user)],
):
    """更新当前登录用户的资料（昵称、头像URL、领域标签、简介）"""
    user = await update_profile(db, current_user, body)
    return ResponseBase(
        message="资料更新成功",
        data=ProfileResponse.model_validate(user),
    )


@router.post(
    "/me/avatar",
    response_model=ResponseBase[ProfileResponse],
    summary="上传头像",
)
async def upload_my_avatar(
    body: AvatarUploadRequest,
    db: Annotated[AsyncSession, Depends(get_db)],
    current_user: Annotated[User, Depends(get_current_user)],
):
    """上传头像（支持 base64 或 URL）"""
    try:
        user = await upload_avatar(db, current_user, body)
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e),
        )
    return ResponseBase(
        message="头像上传成功",
        data=ProfileResponse.model_validate(user),
    )


@router.post(
    "/me/verify",
    response_model=ResponseBase[ProfileResponse],
    summary="实名认证",
)
async def verify_me(
    body: VerifyRequest,
    db: Annotated[AsyncSession, Depends(get_db)],
    current_user: Annotated[User, Depends(get_current_user)],
):
    """实名认证（姓名+身份证号，AES加密存储）"""
    try:
        user = await verify_identity(db, current_user, body)
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=str(e),
        )
    return ResponseBase(
        message="实名认证成功",
        data=ProfileResponse.model_validate(user),
    )


@router.get(
    "/me/stats",
    response_model=ResponseBase[UserStatsResponse],
    summary="获取用户统计",
)
async def get_my_stats(
    db: Annotated[AsyncSession, Depends(get_db)],
    current_user: Annotated[User, Depends(get_current_user)],
):
    """获取当前用户的统计数据"""
    stats = await get_user_stats(db, current_user)
    return ResponseBase(
        data=UserStatsResponse(**stats),
    )


# ============================================================
# 需要所有权检查的路由（管理员或资源所有者可访问）
# ============================================================


@router.put(
    "/{user_id}/profile",
    response_model=ResponseBase[ProfileResponse],
    summary="更新指定用户资料（管理员或本人）",
)
async def update_user_profile(
    user_id: UUID,
    body: ProfileUpdateRequest,
    db: Annotated[AsyncSession, Depends(get_db)],
    current_user: Annotated[User, Depends(OwnershipChecker("user_id"))],
):
    """管理员或本人可更新指定用户的资料"""
    from app.modules.profile.service import get_user_by_id

    target_user = await get_user_by_id(db, user_id)
    if target_user is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="用户不存在",
        )
    user = await update_profile(db, target_user, body)
    return ResponseBase(
        message="资料更新成功",
        data=ProfileResponse.model_validate(user),
    )
