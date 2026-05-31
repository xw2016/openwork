"""
合约生命周期管理服务
处理合约的创建、更新、状态流转、查询等核心业务逻辑
"""

from __future__ import annotations

import random
import string
from datetime import datetime, timezone
from decimal import Decimal
from typing import List, Optional
from uuid import UUID

import structlog
from sqlalchemy import func, select, and_
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.contract import Contract, ContractStatus, TaskType
from app.models.user import UserType
from app.schemas.contract import ContractCreateRequest, ContractUpdateRequest

logger = structlog.get_logger("modules.contract.service")

# ============================================================
# 状态转换规则：定义合法的状态流转
# ============================================================

_VALID_TRANSITIONS = {
    ContractStatus.DRAFT: {ContractStatus.PENDING, ContractStatus.TERMINATED},
    ContractStatus.PENDING: {ContractStatus.IN_PROGRESS, ContractStatus.TERMINATED},
    ContractStatus.IN_PROGRESS: {ContractStatus.REVIEW, ContractStatus.TERMINATED},
    ContractStatus.REVIEW: {
        ContractStatus.COMPLETED,
        ContractStatus.IN_PROGRESS,  # 验收拒绝 -> 回到进行中
        ContractStatus.DISPUTED,
        ContractStatus.TERMINATED,
    },
    # 终态：不允许转换
    ContractStatus.COMPLETED: set(),
    ContractStatus.TERMINATED: set(),
    ContractStatus.DISPUTED: set(),
}


def _validate_transition(current: ContractStatus, target: ContractStatus) -> None:
    """校验状态转换合法性，非法转换抛出 ValueError"""
    allowed = _VALID_TRANSITIONS.get(current, set())
    if target not in allowed:
        raise ValueError(
            f"非法状态转换：{current.value} -> {target.value}，"
            f"允许的目标状态：{[s.value for s in allowed] if allowed else '无（终态）'}"
        )


def _generate_contract_no() -> str:
    """
    生成合约编号，格式：OW-YYYYMMDD-XXXX
    XXXX 为4位随机数字
    """
    date_str = datetime.now(timezone.utc).strftime("%Y%m%d")
    random_suffix = "".join(random.choices(string.digits, k=4))
    return f"OW-{date_str}-{random_suffix}"


# ============================================================
# 合约 CRUD
# ============================================================


async def create_contract(
    db: AsyncSession, employer_id: UUID, data: ContractCreateRequest
) -> Contract:
    """
    创建合约草稿
    自动生成合约编号，初始状态为 draft
    """
    contract = Contract(
        contract_no=_generate_contract_no(),
        employer_id=employer_id,
        title=data.title,
        task_type=data.task_type,
        intent_blueprint=data.intent_blueprint,
        deliverables=[d for d in data.deliverables],
        base_amount=data.base_amount,
        bonus_amount=data.bonus_amount,
        bonus_condition=data.bonus_condition,
        tracking_period=data.tracking_period,
        deadline=data.deadline,
        status=ContractStatus.DRAFT,
    )
    db.add(contract)
    await db.commit()
    await db.refresh(contract)
    logger.info(
        "contract_created",
        contract_id=str(contract.id),
        contract_no=contract.contract_no,
        employer_id=str(employer_id),
    )
    return contract


async def get_contract(db: AsyncSession, contract_id: UUID) -> Optional[Contract]:
    """获取合约详情，不存在返回 None"""
    result = await db.execute(select(Contract).where(Contract.id == contract_id))
    return result.scalar_one_or_none()


async def update_contract(
    db: AsyncSession, contract_id: UUID, data: ContractUpdateRequest
) -> Contract:
    """
    更新合约（仅 draft 状态允许更新）
    """
    contract = await get_contract(db, contract_id)
    if contract is None:
        raise ValueError("合约不存在")
    if contract.status != ContractStatus.DRAFT:
        raise ValueError(f"只有草稿状态的合约可以编辑，当前状态：{contract.status.value}")

    update_data = data.model_dump(exclude_unset=True)
    for field, value in update_data.items():
        if hasattr(contract, field):
            setattr(contract, field, value)

    contract.version += 1
    await db.commit()
    await db.refresh(contract)
    logger.info(
        "contract_updated",
        contract_id=str(contract.id),
        fields=list(update_data.keys()),
    )
    return contract


# ============================================================
# 合约状态流转
# ============================================================


async def publish_contract(db: AsyncSession, contract_id: UUID) -> Contract:
    """
    发布合约：draft -> pending
    """
    contract = await get_contract(db, contract_id)
    if contract is None:
        raise ValueError("合约不存在")
    _validate_transition(contract.status, ContractStatus.PENDING)
    contract.status = ContractStatus.PENDING
    contract.version += 1
    await db.commit()
    await db.refresh(contract)
    logger.info("contract_published", contract_id=str(contract.id))
    return contract


async def accept_contract(
    db: AsyncSession, contract_id: UUID, freelancer_id: UUID
) -> Contract:
    """
    自由职业者接单：pending -> in_progress
    """
    contract = await get_contract(db, contract_id)
    if contract is None:
        raise ValueError("合约不存在")
    _validate_transition(contract.status, ContractStatus.IN_PROGRESS)
    contract.freelancer_id = freelancer_id
    contract.status = ContractStatus.IN_PROGRESS
    contract.version += 1
    await db.commit()
    await db.refresh(contract)
    logger.info(
        "contract_accepted",
        contract_id=str(contract.id),
        freelancer_id=str(freelancer_id),
    )
    return contract


async def submit_for_review(db: AsyncSession, contract_id: UUID) -> Contract:
    """
    提交验收：in_progress -> review
    """
    contract = await get_contract(db, contract_id)
    if contract is None:
        raise ValueError("合约不存在")
    _validate_transition(contract.status, ContractStatus.REVIEW)
    contract.status = ContractStatus.REVIEW
    contract.version += 1
    await db.commit()
    await db.refresh(contract)
    logger.info("contract_submitted_for_review", contract_id=str(contract.id))
    return contract


async def complete_contract(db: AsyncSession, contract_id: UUID) -> Contract:
    """
    完成合约：review -> completed
    """
    contract = await get_contract(db, contract_id)
    if contract is None:
        raise ValueError("合约不存在")
    _validate_transition(contract.status, ContractStatus.COMPLETED)
    contract.status = ContractStatus.COMPLETED
    contract.version += 1
    await db.commit()
    await db.refresh(contract)
    logger.info("contract_completed", contract_id=str(contract.id))
    return contract


async def terminate_contract(db: AsyncSession, contract_id: UUID) -> Contract:
    """
    终止合约：任何非终态 -> terminated
    终态（completed, terminated, disputed）不可终止
    """
    contract = await get_contract(db, contract_id)
    if contract is None:
        raise ValueError("合约不存在")
    _validate_transition(contract.status, ContractStatus.TERMINATED)
    contract.status = ContractStatus.TERMINATED
    contract.version += 1
    await db.commit()
    await db.refresh(contract)
    logger.info("contract_terminated", contract_id=str(contract.id))
    return contract


async def reject_and_resubmit(db: AsyncSession, contract_id: UUID) -> Contract:
    """
    验收拒绝，回退到进行中：review -> in_progress
    """
    contract = await get_contract(db, contract_id)
    if contract is None:
        raise ValueError("合约不存在")
    _validate_transition(contract.status, ContractStatus.IN_PROGRESS)
    contract.status = ContractStatus.IN_PROGRESS
    contract.version += 1
    await db.commit()
    await db.refresh(contract)
    logger.info("contract_rejected_back_to_progress", contract_id=str(contract.id))
    return contract


async def dispute_contract(db: AsyncSession, contract_id: UUID) -> Contract:
    """
    发起争议：review -> disputed
    """
    contract = await get_contract(db, contract_id)
    if contract is None:
        raise ValueError("合约不存在")
    _validate_transition(contract.status, ContractStatus.DISPUTED)
    contract.status = ContractStatus.DISPUTED
    contract.version += 1
    await db.commit()
    await db.refresh(contract)
    logger.info("contract_disputed", contract_id=str(contract.id))
    return contract


# ============================================================
# 合约查询
# ============================================================


async def list_contracts(
    db: AsyncSession,
    user_id: UUID,
    role: Optional[str] = None,
    status: Optional[str] = None,
    page: int = 1,
    size: int = 20,
) -> dict:
    """
    分页查询合约列表
    - role: employer / freelancer，按用户在合约中的角色过滤
    - status: 合约状态过滤
    """
    # 基础查询
    query = select(Contract)
    count_query = select(func.count(Contract.id))

    # 角色过滤
    if role == "employer":
        query = query.where(Contract.employer_id == user_id)
        count_query = count_query.where(Contract.employer_id == user_id)
    elif role == "freelancer":
        query = query.where(Contract.freelancer_id == user_id)
        count_query = count_query.where(Contract.freelancer_id == user_id)
    else:
        # 不指定角色，查询与用户相关的所有合约
        query = query.where(
            (Contract.employer_id == user_id) | (Contract.freelancer_id == user_id)
        )
        count_query = count_query.where(
            (Contract.employer_id == user_id) | (Contract.freelancer_id == user_id)
        )

    # 状态过滤
    if status:
        try:
            status_enum = ContractStatus(status)
            query = query.where(Contract.status == status_enum)
            count_query = count_query.where(Contract.status == status_enum)
        except ValueError:
            raise ValueError(f"无效的合约状态：{status}")

    # 总数
    total_result = await db.execute(count_query)
    total = total_result.scalar() or 0

    # 分页查询
    offset = (page - 1) * size
    query = query.order_by(Contract.created_at.desc()).offset(offset).limit(size)
    result = await db.execute(query)
    contracts = list(result.scalars().all())

    total_pages = (total + size - 1) // size if total > 0 else 0

    return {
        "items": contracts,
        "total": total,
        "page": page,
        "page_size": size,
        "total_pages": total_pages,
    }
