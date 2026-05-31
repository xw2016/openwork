"""
信用评分路由
提供信用分查询、历史记录查看、信用分刷新等端点
"""

from __future__ import annotations

from typing import Annotated
from uuid import UUID

import structlog
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.deps import get_current_user, get_db
from app.core.permissions import Perm
from app.models.user import User
from app.modules.credit import service as credit_service
from app.schemas.common import ResponseBase
from app.schemas.credit import (
    CreditHistoryResponse,
    CreditScoreResponse,
)

logger = structlog.get_logger("modules.credit")

router = APIRouter(prefix="/v1/credit", tags=["信用评分"])


# ============================================================
# GET /v1/credit/score - 获取当前用户信用分
# ============================================================

@router.get(
    "/score",
    response_model=ResponseBase[CreditScoreResponse],
    summary="获取当前用户信用分",
)
async def get_my_credit_score(
    db: Annotated[AsyncSession, Depends(get_db)],
    current_user: Annotated[User, Depends(get_current_user)],
):
    """
    获取当前登录用户的信用评分
    返回信用分、信用等级、是否为新用户等信息
    """
    logger.info("get_my_credit_score", user_id=str(current_user.id))

    # 获取最新信用详情
    credit_detail = current_user.credit_detail or {}
    is_new_user = credit_detail.get("is_new_user", False)

    data = CreditScoreResponse(
        user_id=current_user.id,
        credit_score=current_user.credit_score,
        credit_level=credit_service._get_credit_level(current_user.credit_score),
        is_new_user=is_new_user,
        detail=credit_detail,
    )

    return ResponseBase(data=data)
get_my_credit_score.__permission__ = Perm.CREDIT_SCORE


# ============================================================
# GET /v1/credit/history - 获取信用分历史记录
# ============================================================

@router.get(
    "/history",
    response_model=ResponseBase[CreditHistoryResponse],
    summary="获取信用分历史记录",
)
async def get_my_credit_history(
    db: Annotated[AsyncSession, Depends(get_db)],
    current_user: Annotated[User, Depends(get_current_user)],
):
    """
    获取当前用户的信用分变更历史
    """
    logger.info("get_my_credit_history", user_id=str(current_user.id))

    try:
        history_data = await credit_service.get_credit_history(db, current_user.id)
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(e),
        )

    data = CreditHistoryResponse(
        user_id=history_data["user_id"],
        credit_score=history_data["credit_score"],
        history=history_data["history"],
    )

    return ResponseBase(data=data)
get_my_credit_history.__permission__ = Perm.CREDIT_HISTORY


# ============================================================
# POST /v1/credit/refresh - 刷新当前用户信用分
# ============================================================

@router.post(
    "/refresh",
    response_model=ResponseBase[CreditScoreResponse],
    summary="刷新当前用户信用分",
)
async def refresh_my_credit_score(
    db: Annotated[AsyncSession, Depends(get_db)],
    current_user: Annotated[User, Depends(get_current_user)],
):
    """
    重新计算并刷新当前用户的信用分
    触发信用分重新计算逻辑，更新数据库
    """
    logger.info("refresh_credit_score", user_id=str(current_user.id))

    try:
        updated_user = await credit_service.update_credit_score(db, current_user.id)
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(e),
        )

    credit_detail = updated_user.credit_detail or {}

    data = CreditScoreResponse(
        user_id=updated_user.id,
        credit_score=updated_user.credit_score,
        credit_level=credit_service._get_credit_level(updated_user.credit_score),
        is_new_user=credit_detail.get("is_new_user", False),
        detail=credit_detail,
    )

    return ResponseBase(data=data, message="信用分已刷新")
refresh_my_credit_score.__permission__ = Perm.CREDIT_SCORE


# ============================================================
# GET /v1/credit/users/{user_id}/score - 查看指定用户信用分
# ============================================================

@router.get(
    "/users/{user_id}/score",
    response_model=ResponseBase[CreditScoreResponse],
    summary="查看指定用户信用分",
)
async def get_user_credit_score(
    user_id: UUID,
    db: Annotated[AsyncSession, Depends(get_db)],
    current_user: Annotated[User, Depends(get_current_user)],
):
    """
    查看指定用户的信用分（公开信息）
    任何已登录用户均可查看
    """
    logger.info(
        "get_user_credit_score",
        requester=str(current_user.id),
        target=str(user_id),
    )

    result = await db.execute(select(User).where(User.id == user_id))
    user = result.scalar_one_or_none()
    if user is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="用户不存在",
        )

    credit_detail = user.credit_detail or {}

    data = CreditScoreResponse(
        user_id=user.id,
        credit_score=user.credit_score,
        credit_level=credit_service._get_credit_level(user.credit_score),
        is_new_user=credit_detail.get("is_new_user", False),
        detail=credit_detail,
    )

    return ResponseBase(data=data)
get_user_credit_score.__permission__ = Perm.CREDIT_SCORE
