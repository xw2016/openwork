"""
链上存证路由
提供存证记录的创建、查询、验证等 API 端点
"""

from __future__ import annotations

import uuid
from typing import Annotated

import structlog
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.deps import get_current_user, get_db
from app.core.permissions import Perm
from app.models.user import User
from app.schemas.blockchain import (
    BlockchainRecordCreateRequest,
    BlockchainRecordResponse,
    BlockchainVerifyBody,
)
from app.schemas.common import ResponseBase
from app.modules.blockchain import service as blockchain_service

logger = structlog.get_logger("modules.blockchain.router")

router = APIRouter(prefix="/v1/blockchain", tags=["链上存证"])


@router.post("/record", summary="创建存证记录", status_code=status.HTTP_201_CREATED)
async def create_record(
    body: BlockchainRecordCreateRequest,
    current_user: Annotated[User, Depends(get_current_user)],
    db: AsyncSession = Depends(get_db),
):
    """
    创建链上存证记录
    计算 content_hash 并模拟上链
    """
    record = await blockchain_service.create_record(
        db=db,
        contract_id=body.contract_id,
        node_type=body.node_type,
        content_data=body.content_data,
    )
    return ResponseBase(
        code=201,
        message="存证记录创建成功",
        data=BlockchainRecordResponse.model_validate(record).model_dump(),
    )
create_record.__permission__ = Perm.BLOCKCHAIN_RECORD


@router.get("/records/{record_id}", summary="获取存证详情")
async def get_record(
    record_id: uuid.UUID,
    current_user: Annotated[User, Depends(get_current_user)],
    db: AsyncSession = Depends(get_db),
):
    """获取单条存证记录详情"""
    try:
        record = await blockchain_service.get_record(db, record_id)
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e))

    return ResponseBase(
        data=BlockchainRecordResponse.model_validate(record).model_dump(),
    )
get_record.__permission__ = Perm.BLOCKCHAIN_RECORDS


@router.post("/records/{record_id}/verify", summary="验证存证")
async def verify_record(
    record_id: uuid.UUID,
    body: BlockchainVerifyBody,
    current_user: Annotated[User, Depends(get_current_user)],
    db: AsyncSession = Depends(get_db),
):
    """
    验证存证记录
    重新计算 content_hash 与链上记录比对
    """
    try:
        is_valid = await blockchain_service.verify_record(
            db=db,
            record_id=record_id,
            content_data=body.content_data,
        )
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e))

    return ResponseBase(
        message="验证通过" if is_valid else "验证失败：内容哈希不匹配",
        data={"record_id": str(record_id), "is_valid": is_valid},
    )
verify_record.__permission__ = Perm.BLOCKCHAIN_VERIFY


@router.get("/contracts/{contract_id}/records", summary="合约存证列表")
async def list_records_by_contract(
    contract_id: uuid.UUID,
    current_user: Annotated[User, Depends(get_current_user)],
    db: AsyncSession = Depends(get_db),
):
    """获取指定合约的所有存证记录"""
    records = await blockchain_service.get_records_by_contract(db, contract_id)
    items = [BlockchainRecordResponse.model_validate(r).model_dump() for r in records]
    return ResponseBase(data={"items": items, "total": len(items)})
list_records_by_contract.__permission__ = Perm.BLOCKCHAIN_RECORDS
