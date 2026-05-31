"""
验收模块业务服务

处理验收生命周期：触发验收、拒绝交付物、重提交付物、验收记录查询。
包含合约状态变更逻辑。
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import List, Optional
from uuid import UUID

import structlog
from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.acceptance import AcceptanceRecord, AcceptanceResult
from app.models.contract import Contract, ContractStatus
from app.models.deliverable import AcceptanceStatus, Deliverable
from app.modules.acceptance.engine import (
    AcceptanceEngine,
    EvaluationResult,
    generate_report,
)

logger = structlog.get_logger("modules.acceptance.service")

# 最大修改次数（超过此数值需要人工审核）
MAX_RESUBMIT = 3

# 验收引擎单例
_engine = AcceptanceEngine()


# ============================================================
# 验收核心逻辑
# ============================================================


async def evaluate_contract(
    db: AsyncSession, contract_id: UUID
) -> List[AcceptanceRecord]:
    """
    验收合约的所有交付物

    流程：
    1. 获取合约信息，校验状态
    2. 获取合约下所有已提交的交付物
    3. 逐个交付物进行 AI 验收评估
    4. 创建验收记录
    5. 更新交付物状态
    6. 根据所有交付物结果处理合约状态变更

    :param db: 数据库 session
    :param contract_id: 合约 ID
    :return: 验收记录列表
    :raises ValueError: 合约不存在或状态不合法
    """
    # 获取合约
    contract = await _get_contract(db, contract_id)
    if contract is None:
        raise ValueError("合约不存在")

    # 校验合约状态（必须处于 review 状态才能验收）
    if contract.status != ContractStatus.REVIEW:
        raise ValueError(
            f"合约当前状态为 {contract.status.value}，只有 review 状态的合约可以验收"
        )

    # 获取已提交的交付物
    deliverables = await _get_submitted_deliverables(db, contract_id)
    if not deliverables:
        raise ValueError("该合约没有已提交的交付物，无法验收")

    # 获取当前提交版本（取最大版本号）
    max_version = max(d.submit_version for d in deliverables)

    # 逐个评估交付物
    records: List[AcceptanceRecord] = []
    all_approved = True
    has_rejected = False

    for deliverable in deliverables:
        # 执行规则引擎评估
        eval_result = _engine.evaluate_deliverable(deliverable)

        # 生成验收报告
        report = generate_report(deliverable, eval_result)
        report_dict = report.to_dict()

        # 确定验收结果
        if eval_result.overall == "approved":
            result = AcceptanceResult.APPROVED
            deliverable.acceptance_status = AcceptanceStatus.APPROVED
        else:
            result = AcceptanceResult.REJECTED
            deliverable.acceptance_status = AcceptanceStatus.REJECTED
            all_approved = False
            has_rejected = True

        # 更新交付物验收结果
        deliverable.acceptance_result = eval_result.to_dict()

        # 创建验收记录
        record = AcceptanceRecord(
            contract_id=contract_id,
            submit_version=deliverable.submit_version,
            acceptance_report=report_dict,
            result=result,
            settlement_triggered=False,
        )
        db.add(record)
        records.append(record)

    # 处理合约状态变更
    if all_approved:
        # 全部通过 -> completed
        contract.status = ContractStatus.COMPLETED
        logger.info(
            "contract_auto_completed",
            contract_id=str(contract_id),
            reason="所有交付物验收通过",
        )
    elif has_rejected:
        # 有拒绝 -> in_progress（回退到进行中）
        contract.status = ContractStatus.IN_PROGRESS
        logger.info(
            "contract_back_to_in_progress",
            contract_id=str(contract_id),
            reason="存在未通过验收的交付物",
        )

    contract.version += 1
    await db.commit()

    # 刷新所有记录以获取生成的 id 等字段
    for record in records:
        await db.refresh(record)

    logger.info(
        "contract_evaluated",
        contract_id=str(contract_id),
        deliverables_count=len(deliverables),
        records_count=len(records),
        all_approved=all_approved,
        has_rejected=has_rejected,
        new_contract_status=contract.status.value,
    )

    return records


# ============================================================
# 拒绝交付物
# ============================================================


async def reject_deliverable(
    db: AsyncSession,
    deliverable_id: UUID,
    rejection_reason: str,
) -> AcceptanceRecord:
    """
    拒绝单个交付物

    :param db: 数据库 session
    :param deliverable_id: 交付物 ID
    :param rejection_reason: 拒绝原因
    :return: 验收记录
    :raises ValueError: 交付物不存在或状态不合法
    """
    # 获取交付物
    deliverable = await _get_deliverable(db, deliverable_id)
    if deliverable is None:
        raise ValueError("交付物不存在")

    # 校验交付物状态（必须已提交）
    if deliverable.acceptance_status not in (
        AcceptanceStatus.PENDING,
        AcceptanceStatus.APPROVED,
    ):
        raise ValueError(
            f"交付物当前状态为 {deliverable.acceptance_status.value}，"
            "只有已提交或已通过的交付物可以被拒绝"
        )

    # 更新交付物状态
    deliverable.acceptance_status = AcceptanceStatus.REJECTED
    deliverable.acceptance_result = {
        "rejected_by": "employer",
        "reason": rejection_reason,
        "rejected_at": datetime.now(timezone.utc).isoformat(),
    }
    deliverable.updated_at = datetime.now(timezone.utc)

    # 创建验收记录
    report = {
        "summary": f"交付物「{deliverable.name}」被拒绝",
        "rejection_reason": rejection_reason,
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }

    record = AcceptanceRecord(
        contract_id=deliverable.contract_id,
        submit_version=deliverable.submit_version,
        acceptance_report=report,
        result=AcceptanceResult.REJECTED,
        settlement_triggered=False,
    )
    db.add(record)

    # 更新合约状态为 in_progress（拒绝需要修改重提）
    contract = await _get_contract(db, deliverable.contract_id)
    if contract and contract.status == ContractStatus.REVIEW:
        contract.status = ContractStatus.IN_PROGRESS
        contract.version += 1

    await db.commit()
    await db.refresh(record)

    logger.info(
        "deliverable_rejected",
        deliverable_id=str(deliverable_id),
        deliverable_name=deliverable.name,
        rejection_reason=rejection_reason,
    )

    return record


# ============================================================
# 重提交付物
# ============================================================


async def resubmit_deliverable(
    db: AsyncSession,
    deliverable_id: UUID,
    new_file_url: str,
    new_file_hash: str,
) -> Deliverable:
    """
    重提交付物

    :param db: 数据库 session
    :param deliverable_id: 交付物 ID
    :param new_file_url: 新文件 URL
    :param new_file_hash: 新文件哈希
    :return: 更新后的交付物
    :raises ValueError: 交付物不存在、状态不合法或超过最大修改次数
    """
    # 获取交付物
    deliverable = await _get_deliverable(db, deliverable_id)
    if deliverable is None:
        raise ValueError("交付物不存在")

    # 校验交付物状态（必须为 rejected 或 not_submitted）
    if deliverable.acceptance_status not in (
        AcceptanceStatus.REJECTED,
        AcceptanceStatus.NOT_SUBMITTED,
    ):
        raise ValueError(
            f"交付物当前状态为 {deliverable.acceptance_status.value}，"
            "只有被拒绝或未提交的交付物可以重提"
        )

    # 校验是否超过最大修改次数
    new_version = deliverable.submit_version + 1
    needs_manual_review = False

    if new_version > MAX_RESUBMIT:
        logger.warning(
            "max_resubmit_exceeded",
            deliverable_id=str(deliverable_id),
            current_version=deliverable.submit_version,
            new_version=new_version,
            max_resubmit=MAX_RESUBMIT,
        )
        needs_manual_review = True

    # 更新交付物
    deliverable.file_url = new_file_url
    deliverable.file_hash = new_file_hash
    deliverable.submit_version = new_version
    deliverable.submit_time = datetime.now(timezone.utc)
    deliverable.acceptance_status = AcceptanceStatus.PENDING
    deliverable.acceptance_result = None  # 清空之前的验收结果
    deliverable.updated_at = datetime.now(timezone.utc)

    # 如果超过最大修改次数，标记需要人工审核
    if needs_manual_review:
        deliverable.acceptance_result = {
            "needs_manual_review": True,
            "reason": f"提交版本 {new_version} 超过最大修改次数 {MAX_RESUBMIT}",
            "exceeded_at": datetime.now(timezone.utc).isoformat(),
        }

    # 更新合约状态为 review（重新进入审核）
    contract = await _get_contract(db, deliverable.contract_id)
    if contract and contract.status == ContractStatus.IN_PROGRESS:
        contract.status = ContractStatus.REVIEW
        contract.version += 1

    await db.commit()
    await db.refresh(deliverable)

    logger.info(
        "deliverable_resubmitted",
        deliverable_id=str(deliverable_id),
        deliverable_name=deliverable.name,
        new_version=new_version,
        needs_manual_review=needs_manual_review,
    )

    return deliverable


# ============================================================
# 验收记录查询
# ============================================================


async def get_acceptance_records(
    db: AsyncSession, contract_id: UUID
) -> List[AcceptanceRecord]:
    """
    获取合约的验收记录列表

    :param db: 数据库 session
    :param contract_id: 合约 ID
    :return: 验收记录列表（按创建时间降序）
    """
    result = await db.execute(
        select(AcceptanceRecord)
        .where(AcceptanceRecord.contract_id == contract_id)
        .order_by(AcceptanceRecord.created_at.desc())
    )
    return list(result.scalars().all())


async def get_acceptance_record(
    db: AsyncSession, record_id: UUID
) -> Optional[AcceptanceRecord]:
    """
    获取单个验收记录详情

    :param db: 数据库 session
    :param record_id: 验收记录 ID
    :return: 验收记录，不存在返回 None
    """
    result = await db.execute(
        select(AcceptanceRecord).where(AcceptanceRecord.id == record_id)
    )
    return result.scalar_one_or_none()


# ============================================================
# 内部辅助函数
# ============================================================


async def _get_contract(
    db: AsyncSession, contract_id: UUID
) -> Optional[Contract]:
    """获取合约"""
    result = await db.execute(
        select(Contract).where(Contract.id == contract_id)
    )
    return result.scalar_one_or_none()


async def _get_deliverable(
    db: AsyncSession, deliverable_id: UUID
) -> Optional[Deliverable]:
    """获取交付物"""
    result = await db.execute(
        select(Deliverable).where(Deliverable.id == deliverable_id)
    )
    return result.scalar_one_or_none()


async def _get_submitted_deliverables(
    db: AsyncSession, contract_id: UUID
) -> List[Deliverable]:
    """获取合约下已提交的交付物（非 not_submitted 状态）"""
    result = await db.execute(
        select(Deliverable)
        .where(
            Deliverable.contract_id == contract_id,
            Deliverable.acceptance_status.in_([
                AcceptanceStatus.PENDING,
            ]),
        )
        .order_by(Deliverable.deliverable_index)
    )
    return list(result.scalars().all())
