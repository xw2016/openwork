"""
任务市场路由
市场任务列表（分页+筛选）、任务详情、接单、提交交付物
"""

from __future__ import annotations

import math
from typing import Annotated, Optional
from uuid import UUID

import structlog
from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.deps import get_current_user, get_db
from app.core.permissions import Perm
from app.models.user import User, UserType
from app.modules.market import service as market_service
from app.modules.market import deliverable_ops
from app.schemas.common import PaginatedData, ResponseBase
from app.schemas.deliverable import DeliverableSubmitRequest, DeliverableResponse

logger = structlog.get_logger("modules.market")

router = APIRouter(prefix="/v1/market", tags=["任务市场"])


# ============================================================
# 任务列表（分页+筛选）
# ============================================================


@router.get(
    "/tasks",
    summary="市场任务列表",
)
async def list_tasks(
    db: Annotated[AsyncSession, Depends(get_db)],
    current_user: Annotated[User, Depends(get_current_user)],
    status_filter: Optional[str] = Query(None, alias="status", description="状态过滤"),
    task_type: Optional[str] = Query(None, description="任务类型"),
    keyword: Optional[str] = Query(None, description="关键词搜索标题"),
    min_amount: Optional[float] = Query(None, ge=0, description="最低金额"),
    max_amount: Optional[float] = Query(None, ge=0, description="最高金额"),
    sort: str = Query("created_at_desc", description="排序：created_at_desc/amount_asc/amount_desc"),
    page: int = Query(1, ge=1, description="页码"),
    size: int = Query(20, ge=1, le=100, description="每页条数"),
):
    """
    查询市场任务列表
    默认只展示 pending 状态的合约，支持关键词搜索、金额筛选和排序
    """
    items, total = await market_service.list_market_tasks(
        db,
        status_filter=status_filter,
        task_type=task_type,
        keyword=keyword,
        min_amount=min_amount,
        max_amount=max_amount,
        sort=sort,
        page=page,
        size=size,
    )

    total_pages = math.ceil(total / size) if total > 0 else 0

    return ResponseBase(
        data=PaginatedData(
            items=items,
            total=total,
            page=page,
            page_size=size,
            total_pages=total_pages,
        ),
    )


# ============================================================
# 任务详情
# ============================================================


@router.get(
    "/tasks/{contract_id}",
    summary="任务详情",
)
async def get_task(
    contract_id: UUID,
    db: Annotated[AsyncSession, Depends(get_db)],
    current_user: Annotated[User, Depends(get_current_user)],
):
    """
    获取市场任务详情
    包含雇主昵称和信用分等信息
    """
    task = await market_service.get_market_task_detail(db, contract_id)
    if task is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="任务不存在",
        )

    return ResponseBase(data=task)


# ============================================================
# 接单
# ============================================================


@router.post(
    "/tasks/{contract_id}/bid",
    summary="接单",
)
async def bid_task(
    contract_id: UUID,
    db: Annotated[AsyncSession, Depends(get_db)],
    current_user: Annotated[User, Depends(get_current_user)],
):
    """
    自由职业者接单
    校验合约 pending 状态，freelancer 不能接自己的单
    """
    # 仅自由职业者和管理员可接单
    if current_user.user_type not in (UserType.FREELANCER, UserType.ADMIN):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="只有自由职业者可以接单",
        )

    try:
        contract = await market_service.bid_task(
            db,
            contract_id=contract_id,
            freelancer_id=current_user.id,
        )
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e),
        )

    return ResponseBase(
        message="接单成功",
        data={
            "id": str(contract.id),
            "contract_no": contract.contract_no,
            "freelancer_id": str(contract.freelancer_id),
            "status": contract.status.value,
        },
    )


# ============================================================
# 提交交付物
# ============================================================


@router.post(
    "/tasks/{contract_id}/deliverables/{deliverable_id}/submit",
    summary="提交交付物",
)
async def submit_deliverable(
    contract_id: UUID,
    deliverable_id: UUID,
    body: DeliverableSubmitRequest,
    db: Annotated[AsyncSession, Depends(get_db)],
    current_user: Annotated[User, Depends(get_current_user)],
):
    """
    提交交付物
    校验合约 in_progress，当前用户是 freelancer
    """
    # 仅自由职业者和管理员可提交交付物
    if current_user.user_type not in (UserType.FREELANCER, UserType.ADMIN):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="只有自由职业者可以提交交付物",
        )

    try:
        deliverable = await deliverable_ops.submit_deliverable(
            db,
            contract_id=contract_id,
            deliverable_id=deliverable_id,
            freelancer_id=current_user.id,
            file_url=body.file_url,
            file_hash=body.file_hash,
        )
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e),
        )

    return ResponseBase(
        message="交付物提交成功",
        data=DeliverableResponse.model_validate(deliverable),
    )


# ============================================================
# 权限注解（PermissionMiddleware 读取 __permission__）
# ============================================================

list_tasks.__permission__ = Perm.MARKET_TASKS_LIST
get_task.__permission__ = Perm.MARKET_TASKS_DETAIL
bid_task.__permission__ = Perm.MARKET_BID
submit_deliverable.__permission__ = Perm.CONTRACT_SUBMIT
