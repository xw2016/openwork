"""
任务合约路由
合约的创建、查询、状态流转、交付物管理等全部端点
"""

from __future__ import annotations

from typing import Annotated, List, Optional
from uuid import UUID

import structlog
from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.deps import get_current_user, get_db
from app.core.permissions import Perm
from app.models.contract import ContractStatus
from app.models.user import User, UserType
from app.modules.contract import service as contract_service
from app.modules.contract import deliverable_service
from app.schemas.common import PaginatedData, ResponseBase
from app.schemas.contract import (
    ContractCreateRequest,
    ContractResponse,
    ContractUpdateRequest,
)
from app.schemas.deliverable import DeliverableResponse

logger = structlog.get_logger("modules.contract")

router = APIRouter(prefix="/v1/contracts", tags=["任务合约"])


# ============================================================
# 合约 CRUD 端点
# ============================================================


@router.post(
    "/",
    response_model=ResponseBase[ContractResponse],
    status_code=201,
    summary="创建合约",
)
async def create_contract(
    body: ContractCreateRequest,
    db: Annotated[AsyncSession, Depends(get_db)],
    current_user: Annotated[User, Depends(get_current_user)],
):
    """
    创建合约草稿
    仅雇主角色可创建合约
    """
    # 校验结算配置
    _validate_settlement(body.base_amount, body.bonus_amount)

    contract = await contract_service.create_contract(
        db, employer_id=current_user.id, data=body
    )
    return ResponseBase(
        code=201,
        message="合约创建成功",
        data=ContractResponse.model_validate(contract),
    )


@router.get(
    "/",
    response_model=ResponseBase[PaginatedData[ContractResponse]],
    summary="合约列表",
)
async def list_contracts(
    db: Annotated[AsyncSession, Depends(get_db)],
    current_user: Annotated[User, Depends(get_current_user)],
    role: Optional[str] = Query(None, description="角色过滤：employer/freelancer"),
    contract_status: Optional[str] = Query(
        None, alias="status", description="状态过滤"
    ),
    page: int = Query(1, ge=1, description="页码"),
    size: int = Query(20, ge=1, le=100, description="每页条数"),
):
    """
    获取合约列表
    支持按角色和状态筛选，分页返回
    """
    try:
        result = await contract_service.list_contracts(
            db,
            user_id=current_user.id,
            role=role,
            status=contract_status,
            page=page,
            size=size,
        )
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e),
        )

    items = [ContractResponse.model_validate(c) for c in result["items"]]
    return ResponseBase(
        data=PaginatedData(
            items=items,
            total=result["total"],
            page=result["page"],
            page_size=result["page_size"],
            total_pages=result["total_pages"],
        ),
    )


@router.get(
    "/{contract_id}",
    response_model=ResponseBase[ContractResponse],
    summary="合约详情",
)
async def get_contract(
    contract_id: UUID,
    db: Annotated[AsyncSession, Depends(get_db)],
    current_user: Annotated[User, Depends(get_current_user)],
):
    """获取合约详情"""
    contract = await contract_service.get_contract(db, contract_id)
    if contract is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="合约不存在",
        )

    # 权限校验：只有雇主、对应自由职业者或管理员可查看
    _check_contract_access(current_user, contract)

    return ResponseBase(
        data=ContractResponse.model_validate(contract),
    )


@router.put(
    "/{contract_id}",
    response_model=ResponseBase[ContractResponse],
    summary="更新合约",
)
async def update_contract(
    contract_id: UUID,
    body: ContractUpdateRequest,
    db: Annotated[AsyncSession, Depends(get_db)],
    current_user: Annotated[User, Depends(get_current_user)],
):
    """
    更新合约（仅 draft 状态）
    只有合约创建者（雇主）可更新
    """
    contract = await contract_service.get_contract(db, contract_id)
    if contract is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="合约不存在",
        )
    # 雇主所有权校验
    if current_user.user_type != UserType.ADMIN:
        if contract.employer_id != current_user.id:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="只有合约创建者可以更新合约",
            )

    # 校验结算配置（如果有更新金额）
    base = body.base_amount if body.base_amount is not None else contract.base_amount
    bonus = body.bonus_amount if body.bonus_amount is not None else contract.bonus_amount
    _validate_settlement(base, bonus)

    try:
        updated = await contract_service.update_contract(db, contract_id, body)
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e),
        )

    return ResponseBase(
        message="合约更新成功",
        data=ContractResponse.model_validate(updated),
    )


# ============================================================
# 合约状态流转端点
# ============================================================


@router.post(
    "/{contract_id}/publish",
    response_model=ResponseBase[ContractResponse],
    summary="发布合约",
)
async def publish_contract(
    contract_id: UUID,
    db: Annotated[AsyncSession, Depends(get_db)],
    current_user: Annotated[User, Depends(get_current_user)],
):
    """
    发布合约：draft -> pending
    仅合约创建者（雇主）可发布
    """
    contract = await contract_service.get_contract(db, contract_id)
    if contract is None:
        raise HTTPException(status_code=404, detail="合约不存在")
    if current_user.user_type != UserType.ADMIN:
        if contract.employer_id != current_user.id:
            raise HTTPException(status_code=403, detail="只有合约创建者可以发布")

    try:
        published = await contract_service.publish_contract(db, contract_id)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))

    return ResponseBase(
        message="合约已发布",
        data=ContractResponse.model_validate(published),
    )


@router.post(
    "/{contract_id}/accept",
    response_model=ResponseBase[ContractResponse],
    summary="接单",
)
async def accept_contract(
    contract_id: UUID,
    db: Annotated[AsyncSession, Depends(get_db)],
    current_user: Annotated[User, Depends(get_current_user)],
):
    """
    自由职业者接单：pending -> in_progress
    仅自由职业者可接单
    """
    if current_user.user_type not in (UserType.FREELANCER, UserType.ADMIN):
        raise HTTPException(status_code=403, detail="只有自由职业者可以接单")

    try:
        accepted = await contract_service.accept_contract(
            db, contract_id, freelancer_id=current_user.id
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))

    return ResponseBase(
        message="接单成功",
        data=ContractResponse.model_validate(accepted),
    )


@router.post(
    "/{contract_id}/submit",
    response_model=ResponseBase[ContractResponse],
    summary="提交验收",
)
async def submit_for_review(
    contract_id: UUID,
    db: Annotated[AsyncSession, Depends(get_db)],
    current_user: Annotated[User, Depends(get_current_user)],
):
    """
    提交验收：in_progress -> review
    仅合约的自由职业者可提交
    """
    contract = await contract_service.get_contract(db, contract_id)
    if contract is None:
        raise HTTPException(status_code=404, detail="合约不存在")
    if current_user.user_type != UserType.ADMIN:
        if contract.freelancer_id != current_user.id:
            raise HTTPException(status_code=403, detail="只有合约承接者可以提交验收")

    try:
        submitted = await contract_service.submit_for_review(db, contract_id)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))

    return ResponseBase(
        message="已提交验收",
        data=ContractResponse.model_validate(submitted),
    )


@router.post(
    "/{contract_id}/complete",
    response_model=ResponseBase[ContractResponse],
    summary="完成合约",
)
async def complete_contract(
    contract_id: UUID,
    db: Annotated[AsyncSession, Depends(get_db)],
    current_user: Annotated[User, Depends(get_current_user)],
):
    """
    验收通过，完成合约：review -> completed
    仅雇主可确认完成
    """
    contract = await contract_service.get_contract(db, contract_id)
    if contract is None:
        raise HTTPException(status_code=404, detail="合约不存在")
    if current_user.user_type != UserType.ADMIN:
        if contract.employer_id != current_user.id:
            raise HTTPException(status_code=403, detail="只有雇主可以确认完成")

    try:
        completed = await contract_service.complete_contract(db, contract_id)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))

    return ResponseBase(
        message="合约已完成",
        data=ContractResponse.model_validate(completed),
    )


@router.post(
    "/{contract_id}/terminate",
    response_model=ResponseBase[ContractResponse],
    summary="终止合约",
)
async def terminate_contract(
    contract_id: UUID,
    db: Annotated[AsyncSession, Depends(get_db)],
    current_user: Annotated[User, Depends(get_current_user)],
):
    """
    终止合约：任何非终态 -> terminated
    雇主或管理员可终止
    """
    contract = await contract_service.get_contract(db, contract_id)
    if contract is None:
        raise HTTPException(status_code=404, detail="合约不存在")
    if current_user.user_type != UserType.ADMIN:
        if contract.employer_id != current_user.id:
            raise HTTPException(status_code=403, detail="只有雇主可以终止合约")

    try:
        terminated = await contract_service.terminate_contract(db, contract_id)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))

    return ResponseBase(
        message="合约已终止",
        data=ContractResponse.model_validate(terminated),
    )


# ============================================================
# 交付物管理端点
# ============================================================


@router.get(
    "/{contract_id}/deliverables",
    response_model=ResponseBase[List[DeliverableResponse]],
    summary="交付物列表",
)
async def get_deliverables(
    contract_id: UUID,
    db: Annotated[AsyncSession, Depends(get_db)],
    current_user: Annotated[User, Depends(get_current_user)],
):
    """获取合约的交付物列表"""
    contract = await contract_service.get_contract(db, contract_id)
    if contract is None:
        raise HTTPException(status_code=404, detail="合约不存在")

    # 权限校验
    _check_contract_access(current_user, contract)

    deliverables = await deliverable_service.get_deliverables(db, contract_id)
    return ResponseBase(
        data=[DeliverableResponse.model_validate(d) for d in deliverables],
    )


@router.post(
    "/{contract_id}/deliverables",
    response_model=ResponseBase[List[DeliverableResponse]],
    status_code=201,
    summary="生成交付物清单",
)
async def generate_deliverables(
    contract_id: UUID,
    db: Annotated[AsyncSession, Depends(get_db)],
    current_user: Annotated[User, Depends(get_current_user)],
):
    """
    根据合约的任务类型和蓝图自动生成交付物清单
    仅合约创建者（雇主）可操作
    """
    contract = await contract_service.get_contract(db, contract_id)
    if contract is None:
        raise HTTPException(status_code=404, detail="合约不存在")
    if current_user.user_type != UserType.ADMIN:
        if contract.employer_id != current_user.id:
            raise HTTPException(status_code=403, detail="只有雇主可以生成交付物清单")

    # 检查是否已有交付物
    existing = await deliverable_service.get_deliverables(db, contract_id)
    if existing:
        raise HTTPException(
            status_code=409,
            detail="该合约已有交付物清单，请勿重复生成",
        )

    # 根据任务类型和蓝图生成
    deliverables_data = deliverable_service.generate_deliverables(
        task_type=contract.task_type.value,
        blueprint=contract.intent_blueprint,
    )

    created = await deliverable_service.create_deliverables(
        db, contract_id, deliverables_data
    )

    return ResponseBase(
        code=201,
        message="交付物清单生成成功",
        data=[DeliverableResponse.model_validate(d) for d in created],
    )


# ============================================================
# 内部辅助函数
# ============================================================


def _validate_settlement(base_amount, bonus_amount) -> None:
    """
    校验结算配置
    - base_amount 必须 > 0
    """
    if base_amount is not None and base_amount <= 0:
        raise HTTPException(
            status_code=400,
            detail="基础金额必须大于0",
        )


def _check_contract_access(user: User, contract) -> None:
    """校验用户是否有权查看合约"""
    if user.user_type == UserType.ADMIN:
        return
    if contract.employer_id == user.id:
        return
    if contract.freelancer_id and contract.freelancer_id == user.id:
        return
    raise HTTPException(
        status_code=403,
        detail="无权查看此合约",
    )


def calculate_commission(base_amount, commission_rate) -> float:
    """
    计算佣金
    :param base_amount: 基础金额
    :param commission_rate: 佣金比例
    :return: 佣金金额
    """
    return float(base_amount * commission_rate)


def calculate_total_payable(base_amount, bonus_amount, commission_rate) -> dict:
    """
    计算总应付金额
    :return: 包含各金额明细的字典
    """
    commission = calculate_commission(base_amount, commission_rate)
    total = float(base_amount) + float(bonus_amount) - commission
    return {
        "base_amount": float(base_amount),
        "bonus_amount": float(bonus_amount),
        "commission_rate": float(commission_rate),
        "commission": round(commission, 2),
        "total_payable": round(total, 2),
    }


def validate_settlement_config(data: dict) -> None:
    """
    校验结算配置
    - base_amount 必须 > 0
    - commission_rate 必须在 0 ~ 0.3 之间
    """
    base_amount = data.get("base_amount")
    if base_amount is not None and base_amount <= 0:
        raise ValueError("base_amount 必须大于 0")

    commission_rate = data.get("commission_rate")
    if commission_rate is not None:
        if commission_rate < 0 or commission_rate > 0.3:
            raise ValueError("commission_rate 必须在 0 ~ 0.3 之间")


# 将路由函数附上权限注解（PermissionMiddleware 会读取 __permission__）
create_contract.__permission__ = Perm.CONTRACT_CREATE
list_contracts.__permission__ = Perm.CONTRACT_LIST
get_contract.__permission__ = Perm.CONTRACT_DETAIL
update_contract.__permission__ = Perm.CONTRACT_UPDATE
publish_contract.__permission__ = Perm.CONTRACT_UPDATE
accept_contract.__permission__ = Perm.CONTRACT_ACCEPT
submit_for_review.__permission__ = Perm.CONTRACT_SUBMIT
complete_contract.__permission__ = Perm.CONTRACT_CONFIRM
terminate_contract.__permission__ = Perm.CONTRACT_UPDATE
get_deliverables.__permission__ = Perm.CONTRACT_DETAIL
generate_deliverables.__permission__ = Perm.CONTRACT_UPDATE
