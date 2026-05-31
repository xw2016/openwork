"""
任务市场服务
处理市场任务列表查询、接单等核心业务逻辑
"""

from __future__ import annotations

from decimal import Decimal
from typing import List, Optional, Tuple
from uuid import UUID

import re as _re
import structlog
from sqlalchemy import func, select, and_
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.contract import Contract, ContractStatus, TaskType
from app.models.user import User

logger = structlog.get_logger("modules.market.service")


# ============================================================
# Helpers
# ============================================================


def _escape_like(value: str) -> str:
    """Escape LIKE special characters % _ and \\."""
    return value.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")


# ============================================================
# 市场任务查询
# ============================================================


async def list_market_tasks(
    db: AsyncSession,
    status_filter: Optional[str] = None,
    task_type: Optional[str] = None,
    keyword: Optional[str] = None,
    min_amount: Optional[float] = None,
    max_amount: Optional[float] = None,
    sort: str = "created_at_desc",
    page: int = 1,
    size: int = 20,
) -> Tuple[List[dict], int]:
    """
    查询市场任务列表（仅展示 pending 状态的合约）

    返回值：(任务列表, 总数)
    每个任务包含雇主昵称和信用分
    """
    # 基础查询：关联 Contract 和 User（雇主）
    base_conditions = [Contract.status == ContractStatus.PENDING]

    # 状态过滤（市场默认只展示 pending，但允许前端显式传入）
    if status_filter:
        try:
            target_status = ContractStatus(status_filter)
            base_conditions = [Contract.status == target_status]
        except ValueError:
            logger.warning("invalid_status_filter", status=status_filter)
            # 回退到默认 pending
            base_conditions = [Contract.status == ContractStatus.PENDING]

    # 任务类型过滤
    if task_type:
        try:
            target_type = TaskType(task_type)
            base_conditions.append(Contract.task_type == target_type)
        except ValueError:
            logger.warning("invalid_task_type", task_type=task_type)

    # 关键词搜索标题
    if keyword:
        safe_keyword = _escape_like(keyword)
        base_conditions.append(Contract.title.ilike(f"%{safe_keyword}%"))

    # 金额范围筛选
    if min_amount is not None:
        base_conditions.append(Contract.base_amount >= Decimal(str(min_amount)))
    if max_amount is not None:
        base_conditions.append(Contract.base_amount <= Decimal(str(max_amount)))

    where_clause = and_(*base_conditions)

    # 总数查询
    count_query = select(func.count(Contract.id)).where(where_clause)
    total_result = await db.execute(count_query)
    total = total_result.scalar() or 0

    # 排序
    order_map = {
        "created_at_desc": Contract.created_at.desc(),
        "amount_asc": Contract.base_amount.asc(),
        "amount_desc": Contract.base_amount.desc(),
    }
    order_clause = order_map.get(sort, Contract.created_at.desc())

    # 分页查询，关联雇主信息
    offset = (page - 1) * size
    query = (
        select(Contract, User.nickname, User.credit_score)
        .join(User, Contract.employer_id == User.id)
        .where(where_clause)
        .order_by(order_clause)
        .offset(offset)
        .limit(size)
    )
    result = await db.execute(query)
    rows = result.all()

    # 组装返回数据
    items = []
    for row in rows:
        contract = row[0]
        employer_nickname = row[1]
        employer_credit_score = row[2]
        items.append({
            "id": str(contract.id),
            "contract_no": contract.contract_no,
            "employer_id": str(contract.employer_id),
            "freelancer_id": str(contract.freelancer_id) if contract.freelancer_id else None,
            "title": contract.title,
            "task_type": contract.task_type.value,
            "base_amount": str(contract.base_amount),
            "bonus_amount": str(contract.bonus_amount),
            "deadline": contract.deadline.isoformat() if contract.deadline else None,
            "status": contract.status.value,
            "created_at": contract.created_at.isoformat(),
            "employer_nickname": employer_nickname,
            "employer_credit_score": employer_credit_score,
        })

    logger.info(
        "market_tasks_listed",
        total=total,
        page=page,
        size=size,
        filters={"task_type": task_type, "keyword": keyword},
    )
    return items, total


async def get_market_task_detail(
    db: AsyncSession,
    contract_id: UUID,
) -> Optional[dict]:
    """
    获取市场任务详情（含雇主信息）
    不存在返回 None
    """
    query = (
        select(Contract, User.nickname, User.credit_score)
        .join(User, Contract.employer_id == User.id)
        .where(Contract.id == contract_id)
    )
    result = await db.execute(query)
    row = result.one_or_none()

    if row is None:
        return None

    contract = row[0]
    employer_nickname = row[1]
    employer_credit_score = row[2]

    return {
        "id": str(contract.id),
        "contract_no": contract.contract_no,
        "employer_id": str(contract.employer_id),
        "freelancer_id": str(contract.freelancer_id) if contract.freelancer_id else None,
        "title": contract.title,
        "task_type": contract.task_type.value,
        "intent_blueprint": contract.intent_blueprint,
        "deliverables": contract.deliverables,
        "base_amount": str(contract.base_amount),
        "bonus_amount": str(contract.bonus_amount),
        "bonus_condition": contract.bonus_condition,
        "commission_rate": str(contract.commission_rate),
        "deadline": contract.deadline.isoformat() if contract.deadline else None,
        "status": contract.status.value,
        "version": contract.version,
        "created_at": contract.created_at.isoformat(),
        "updated_at": contract.updated_at.isoformat(),
        "employer_nickname": employer_nickname,
        "employer_credit_score": employer_credit_score,
    }


# ============================================================
# 接单
# ============================================================


async def bid_task(
    db: AsyncSession,
    contract_id: UUID,
    freelancer_id: UUID,
) -> Contract:
    """
    自由职业者接单

    校验：
    - 合约必须处于 pending 状态
    - freelancer 不能接自己发布的单

    更新：
    - contract.freelancer_id = freelancer_id
    - contract.status = in_progress
    """
    result = await db.execute(
        select(Contract).where(Contract.id == contract_id).with_for_update()
    )
    contract = result.scalar_one_or_none()

    if contract is None:
        raise ValueError("合约不存在")

    # 校验合约状态
    if contract.status != ContractStatus.PENDING:
        raise ValueError(
            f"合约当前状态为 {contract.status.value}，无法接单"
        )

    # 校验不能接自己的单
    if contract.employer_id == freelancer_id:
        raise ValueError("不能接自己发布的任务")

    # 更新合约
    contract.freelancer_id = freelancer_id
    contract.status = ContractStatus.IN_PROGRESS
    contract.version += 1

    await db.commit()
    await db.refresh(contract)

    logger.info(
        "task_bid_success",
        contract_id=str(contract.id),
        freelancer_id=str(freelancer_id),
        employer_id=str(contract.employer_id),
    )
    return contract
