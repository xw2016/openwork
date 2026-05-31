"""
AI验收路由

提供验收评估、验收记录查询、拒绝交付物、重提交付物等端点。
"""

from __future__ import annotations

from typing import Annotated, List
from uuid import UUID

import structlog
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.deps import get_current_user, get_db
from app.core.permissions import Perm
from app.models.user import User, UserType
from app.modules.acceptance import service as acceptance_service
from app.schemas.acceptance import (
    AcceptanceRecordResponse,
    RejectDeliverableRequest,
    ResubmitDeliverableRequest,
)
from app.schemas.common import ResponseBase
from app.schemas.deliverable import DeliverableResponse

logger = structlog.get_logger("modules.acceptance")

router = APIRouter(prefix="/v1/acceptance", tags=["AI验收"])


# ============================================================
# 验收评估端点
# ============================================================


@router.post(
    "/contracts/{contract_id}/evaluate",
    response_model=ResponseBase[List[AcceptanceRecordResponse]],
    summary="触发合约验收",
)
async def evaluate_contract(
    contract_id: UUID,
    db: Annotated[AsyncSession, Depends(get_db)],
    current_user: Annotated[User, Depends(get_current_user)],
):
    """
    触发合约所有交付物的 AI 验收评估

    - 仅雇主或管理员可触发验收
    - 合约必须处于 review 状态
    - 使用规则引擎对每个交付物进行逐项检查
    - 全部通过 -> 合约自动完成
    - 有拒绝 -> 合约回退到进行中
    """
    # 权限校验：仅雇主或管理员可触发验收
    if current_user.user_type not in (UserType.EMPLOYER, UserType.ADMIN):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="只有雇主或管理员可以触发验收",
        )

    try:
        records = await acceptance_service.evaluate_contract(db, contract_id)
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e),
        )

    return ResponseBase(
        message="验收评估完成",
        data=[AcceptanceRecordResponse.model_validate(r) for r in records],
    )

evaluate_contract.__permission__ = Perm.ACCEPTANCE_EVALUATE


# ============================================================
# 验收记录查询端点
# ============================================================


@router.get(
    "/contracts/{contract_id}/records",
    response_model=ResponseBase[List[AcceptanceRecordResponse]],
    summary="验收记录列表",
)
async def list_records(
    contract_id: UUID,
    db: Annotated[AsyncSession, Depends(get_db)],
    current_user: Annotated[User, Depends(get_current_user)],
):
    """
    获取合约的验收记录列表

    - 雇主、管理员、以及合约关联的自由职业者可查看
    - 按创建时间降序排列
    """
    records = await acceptance_service.get_acceptance_records(db, contract_id)
    return ResponseBase(
        data=[AcceptanceRecordResponse.model_validate(r) for r in records],
    )

list_records.__permission__ = Perm.ACCEPTANCE_RECORDS_LIST


@router.get(
    "/records/{record_id}",
    response_model=ResponseBase[AcceptanceRecordResponse],
    summary="验收记录详情",
)
async def get_record(
    record_id: UUID,
    db: Annotated[AsyncSession, Depends(get_db)],
    current_user: Annotated[User, Depends(get_current_user)],
):
    """
    获取单个验收记录详情

    - 包含完整的验收报告
    """
    record = await acceptance_service.get_acceptance_record(db, record_id)
    if record is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="验收记录不存在",
        )

    return ResponseBase(
        data=AcceptanceRecordResponse.model_validate(record),
    )

get_record.__permission__ = Perm.ACCEPTANCE_RECORDS_DETAIL


# ============================================================
# 拒绝交付物端点
# ============================================================


@router.post(
    "/deliverables/{deliverable_id}/reject",
    response_model=ResponseBase[AcceptanceRecordResponse],
    summary="拒绝交付物",
)
async def reject_deliverable(
    deliverable_id: UUID,
    body: RejectDeliverableRequest,
    db: Annotated[AsyncSession, Depends(get_db)],
    current_user: Annotated[User, Depends(get_current_user)],
):
    """
    拒绝单个交付物

    - 仅雇主或管理员可拒绝
    - 记录拒绝原因
    - 合约状态回退到 in_progress
    """
    # 权限校验
    if current_user.user_type not in (UserType.EMPLOYER, UserType.ADMIN):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="只有雇主或管理员可以拒绝交付物",
        )

    try:
        record = await acceptance_service.reject_deliverable(
            db, deliverable_id, body.rejection_reason
        )
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e),
        )

    return ResponseBase(
        message="交付物已拒绝",
        data=AcceptanceRecordResponse.model_validate(record),
    )

reject_deliverable.__permission__ = Perm.ACCEPTANCE_REJECT


# ============================================================
# 重提交付物端点
# ============================================================


@router.post(
    "/deliverables/{deliverable_id}/resubmit",
    response_model=ResponseBase[DeliverableResponse],
    summary="重提交付物",
)
async def resubmit_deliverable(
    deliverable_id: UUID,
    body: ResubmitDeliverableRequest,
    db: Annotated[AsyncSession, Depends(get_db)],
    current_user: Annotated[User, Depends(get_current_user)],
):
    """
    重提交付物

    - 仅自由职业者可重提
    - 交付物必须处于 rejected 状态
    - 提交版本递增，超过 MAX_RESUBMIT 次后标记需要人工审核
    - 合约状态回到 review
    """
    # 权限校验
    if current_user.user_type not in (UserType.FREELANCER, UserType.ADMIN):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="只有自由职业者可以重提交付物",
        )

    try:
        deliverable = await acceptance_service.resubmit_deliverable(
            db, deliverable_id, body.file_url, body.file_hash
        )
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e),
        )

    return ResponseBase(
        message="交付物已重提",
        data=DeliverableResponse.model_validate(deliverable),
    )

resubmit_deliverable.__permission__ = Perm.ACCEPTANCE_RESUBMIT
