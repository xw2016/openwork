"""
市场模块交付物操作
处理自由职业者在市场流程中提交交付物的逻辑
"""

from __future__ import annotations

from datetime import datetime, timezone
from uuid import UUID

import structlog
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.contract import Contract, ContractStatus
from app.models.deliverable import AcceptanceStatus, Deliverable

logger = structlog.get_logger("modules.market.deliverable_ops")


async def submit_deliverable(
    db: AsyncSession,
    contract_id: UUID,
    deliverable_id: UUID,
    freelancer_id: UUID,
    file_url: str,
    file_hash: str | None = None,
) -> Deliverable:
    """
    提交交付物

    校验：
    - 合约必须处于 in_progress 状态
    - 当前用户必须是该合约的 freelancer
    - 交付物必须属于该合约

    更新：
    - file_url, file_hash
    - submit_version += 1
    - submit_time = now
    - acceptance_status = pending
    """
    # 查询合约
    contract_result = await db.execute(
        select(Contract).where(Contract.id == contract_id)
    )
    contract = contract_result.scalar_one_or_none()

    if contract is None:
        raise ValueError("合约不存在")

    # 校验合约状态
    if contract.status != ContractStatus.IN_PROGRESS:
        raise ValueError(
            f"合约当前状态为 {contract.status.value}，无法提交交付物"
        )

    # 校验当前用户是该合约的 freelancer
    if contract.freelancer_id != freelancer_id:
        raise ValueError("只有合约承接者可以提交交付物")

    # 查询交付物
    deliverable_result = await db.execute(
        select(Deliverable).where(
            Deliverable.id == deliverable_id,
            Deliverable.contract_id == contract_id,
        )
    )
    deliverable = deliverable_result.scalar_one_or_none()

    if deliverable is None:
        raise ValueError("交付物不存在或不属于该合约")

    # 更新交付物
    deliverable.file_url = file_url
    deliverable.file_hash = file_hash
    deliverable.submit_version += 1
    deliverable.submit_time = datetime.now(timezone.utc)
    deliverable.acceptance_status = AcceptanceStatus.PENDING

    await db.commit()
    await db.refresh(deliverable)

    logger.info(
        "deliverable_submitted",
        deliverable_id=str(deliverable.id),
        contract_id=str(contract_id),
        freelancer_id=str(freelancer_id),
        submit_version=deliverable.submit_version,
    )
    return deliverable
