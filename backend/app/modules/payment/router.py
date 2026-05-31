"""
资金结算路由
资金托管、释放、退款、交易记录查询等端点
"""

from __future__ import annotations

from decimal import Decimal
from typing import Annotated, List
from uuid import UUID

import structlog
from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.deps import get_current_user, get_db
from app.core.permissions import Perm
from app.models.user import User, UserType
from app.modules.payment import service as payment_service
from app.schemas.common import PaginatedData, ResponseBase
from app.schemas.transaction import TransactionResponse

logger = structlog.get_logger("modules.payment")

router = APIRouter(prefix="/v1/payment", tags=["资金结算"])


# ============================================================
# 请求模型
# ============================================================


class EscrowRequest(BaseModel):
    """创建资金托管请求"""
    contract_id: UUID = Field(..., description="关联合约ID")
    amount: Decimal = Field(..., gt=0, description="托管金额（元）")


class RefundRequest(BaseModel):
    """退款请求"""
    reason: str = Field("", description="退款原因")


# ============================================================
# 资金托管端点
# ============================================================


@router.post(
    "/escrow",
    response_model=ResponseBase[TransactionResponse],
    status_code=201,
    summary="创建资金托管",
)
async def escrow_funds(
    body: EscrowRequest,
    db: Annotated[AsyncSession, Depends(get_db)],
    current_user: Annotated[User, Depends(get_current_user)],
):
    """
    雇主预付资金 -> 冻结
    创建 escrow 类型交易，status=pending
    """
    try:
        escrow = await payment_service.create_escrow(
            db,
            contract_id=body.contract_id,
            employer_id=current_user.id,
            amount=body.amount,
        )
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e),
        )

    return ResponseBase(
        code=201,
        message="资金托管创建成功",
        data=TransactionResponse.model_validate(escrow),
    )
escrow_funds.__permission__ = Perm.PAYMENT_ESCROW


# ============================================================
# 释放资金端点
# ============================================================


@router.post(
    "/contracts/{contract_id}/release",
    response_model=ResponseBase[TransactionResponse],
    summary="释放资金",
)
async def release_funds(
    contract_id: UUID,
    db: Annotated[AsyncSession, Depends(get_db)],
    current_user: Annotated[User, Depends(get_current_user)],
):
    """
    验收通过后释放资金给自由职业者
    计算佣金，创建 payment 类型交易
    """
    try:
        payment = await payment_service.release_escrow(
            db,
            contract_id=contract_id,
        )
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e),
        )

    return ResponseBase(
        message="资金释放成功",
        data=TransactionResponse.model_validate(payment),
    )
release_funds.__permission__ = Perm.PAYMENT_RELEASE


# ============================================================
# 退款端点
# ============================================================


@router.post(
    "/contracts/{contract_id}/refund",
    response_model=ResponseBase[TransactionResponse],
    summary="退款",
)
async def refund(
    contract_id: UUID,
    body: RefundRequest,
    db: Annotated[AsyncSession, Depends(get_db)],
    current_user: Annotated[User, Depends(get_current_user)],
):
    """
    合约终止时退还雇主预付资金
    创建 refund 类型交易
    """
    try:
        refund_tx = await payment_service.refund_escrow(
            db,
            contract_id=contract_id,
            reason=body.reason,
        )
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e),
        )

    return ResponseBase(
        message="退款成功",
        data=TransactionResponse.model_validate(refund_tx),
    )
refund.__permission__ = Perm.PAYMENT_REFUND


# ============================================================
# 交易记录查询端点
# ============================================================


@router.get(
    "/contracts/{contract_id}/transactions",
    response_model=ResponseBase[PaginatedData[TransactionResponse]],
    summary="交易记录列表",
)
async def list_transactions(
    contract_id: UUID,
    db: Annotated[AsyncSession, Depends(get_db)],
    current_user: Annotated[User, Depends(get_current_user)],
    page: int = Query(1, ge=1, description="页码"),
    size: int = Query(20, ge=1, le=100, description="每页条数"),
):
    """
    获取合约的交易记录列表
    支持分页查询
    """
    result = await payment_service.list_transactions(
        db,
        contract_id=contract_id,
        page=page,
        size=size,
    )

    items = [TransactionResponse.model_validate(t) for t in result["items"]]
    return ResponseBase(
        data=PaginatedData(
            items=items,
            total=result["total"],
            page=result["page"],
            page_size=result["page_size"],
            total_pages=result["total_pages"],
        ),
    )
list_transactions.__permission__ = Perm.PAYMENT_TRANSACTIONS
