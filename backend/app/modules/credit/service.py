"""
信用评分计算服务
包含雇主和自由职业者的信用分计算逻辑

信用分范围：0-1000
冷启动策略：新用户（<5个任务）默认 700 分
"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import Optional

import structlog
from sqlalchemy import select, func, and_
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm.attributes import flag_modified

from app.models.acceptance import AcceptanceRecord, AcceptanceResult
from app.models.contract import Contract, ContractStatus
from app.models.transaction import Transaction, TransactionType
from app.models.deliverable import Deliverable, AcceptanceStatus
from app.models.user import User, UserType

logger = structlog.get_logger("modules.credit.service")

# ============================================================
# 常量
# ============================================================

# 冷启动默认分数
COLD_START_SCORE = 700

# 冷启动阈值：少于此任务数视为新用户
COLD_START_THRESHOLD = 5

# 基础分
BASE_SCORE = 600

# 默认雇主评分（评分维度暂时用默认值）
DEFAULT_RATING = 80


# ============================================================
# 信用等级映射
# ============================================================

def _get_credit_level(score: int) -> str:
    """根据信用分返回信用等级"""
    if score >= 900:
        return "优秀"
    elif score >= 800:
        return "良好"
    elif score >= 700:
        return "中等"
    elif score >= 600:
        return "一般"
    elif score >= 400:
        return "较差"
    else:
        return "极差"


# ============================================================
# 雇主信用分计算
# ============================================================

async def calculate_employer_score(db: AsyncSession, employer_id: uuid.UUID) -> int:
    """
    计算雇主信用分

    公式：完成率×40 + 结算效率×30 + 拒付扣分×30
    - 完成率 = completed_contracts / total_contracts * 100
    - 结算效率 = 按时结算次数 / 总结算次数 * 100（验收通过后按时释放资金）
    - 拒付扣分 = 退款次数 / 总合约数 * 100（退款越多扣分越多）
    - 基础分 600，各项加权后映射到 0-1000 分
    """
    # 查询雇主的所有合约
    total_result = await db.execute(
        select(func.count(Contract.id)).where(Contract.employer_id == employer_id)
    )
    total_contracts = total_result.scalar() or 0

    if total_contracts == 0:
        return COLD_START_SCORE

    # 完成率：已完成合约数
    completed_result = await db.execute(
        select(func.count(Contract.id)).where(
            and_(
                Contract.employer_id == employer_id,
                Contract.status == ContractStatus.COMPLETED,
            )
        )
    )
    completed_contracts = completed_result.scalar() or 0
    completion_rate = (completed_contracts / total_contracts) * 100

    # 结算效率：验收通过且 settlement_triggered=True 的次数
    # 查询雇主所有已完成合约的 ID
    contract_ids_result = await db.execute(
        select(Contract.id).where(
            and_(
                Contract.employer_id == employer_id,
                Contract.status == ContractStatus.COMPLETED,
            )
        )
    )
    completed_contract_ids = [row[0] for row in contract_ids_result.fetchall()]

    total_settlements = 0
    on_time_settlements = 0
    if completed_contract_ids:
        # 总验收通过次数
        acceptance_result = await db.execute(
            select(func.count(AcceptanceRecord.id)).where(
                and_(
                    AcceptanceRecord.contract_id.in_(completed_contract_ids),
                    AcceptanceRecord.result == AcceptanceResult.APPROVED,
                )
            )
        )
        total_settlements = acceptance_result.scalar() or 0

        # 按时结算：验收通过且触发了结算
        on_time_result = await db.execute(
            select(func.count(AcceptanceRecord.id)).where(
                and_(
                    AcceptanceRecord.contract_id.in_(completed_contract_ids),
                    AcceptanceRecord.result == AcceptanceResult.APPROVED,
                    AcceptanceRecord.settlement_triggered == True,  # noqa: E712
                )
            )
        )
        on_time_settlements = on_time_result.scalar() or 0

    settlement_efficiency = (
        (on_time_settlements / total_settlements * 100)
        if total_settlements > 0
        else 100.0  # 无结算记录视为满分
    )

    # 拒付扣分：退款交易数
    refund_result = await db.execute(
        select(func.count(Transaction.id)).where(
            and_(
                Transaction.from_user_id == employer_id,
                Transaction.transaction_type == TransactionType.REFUND,
            )
        )
    )
    refund_count = refund_result.scalar() or 0
    # 拒付率越高扣分越多，所以这里是 100 - 拒付率
    refund_penalty_rate = (refund_count / total_contracts) * 100
    refund_score = max(0.0, 100.0 - refund_penalty_rate)

    # 加权计算
    weighted_score = (
        completion_rate * 0.4
        + settlement_efficiency * 0.3
        + refund_score * 0.3
    )

    # 映射到 0-1000：基础分 600 + 加权分映射的增量
    # weighted_score 范围 0-100，映射到 0-400 的增量
    final_score = int(BASE_SCORE + weighted_score * 4)
    final_score = max(0, min(1000, final_score))

    logger.info(
        "employer_score_calculated",
        employer_id=str(employer_id),
        total_contracts=total_contracts,
        completed_contracts=completed_contracts,
        completion_rate=round(completion_rate, 2),
        settlement_efficiency=round(settlement_efficiency, 2),
        refund_score=round(refund_score, 2),
        final_score=final_score,
    )

    return final_score


# ============================================================
# 自由职业者信用分计算
# ============================================================

async def calculate_freelancer_score(db: AsyncSession, freelancer_id: uuid.UUID) -> int:
    """
    计算自由职业者信用分

    公式：一次通过率×35 + 延迟×25 + 完成率×25 + 评分×15
    - 一次通过率 = 首次验收通过次数 / 总提交次数 * 100
    - 延迟 = 未延迟完成次数 / 总完成次数 * 100
    - 完成率 = completed_contracts / total_contracts * 100
    - 评分 = 平均雇主评分（暂时用 0-100 的默认值 80）
    - 映射到 0-1000 分
    """
    # 查询自由职业者的所有合约
    total_result = await db.execute(
        select(func.count(Contract.id)).where(Contract.freelancer_id == freelancer_id)
    )
    total_contracts = total_result.scalar() or 0

    if total_contracts == 0:
        return COLD_START_SCORE

    # 完成率
    completed_result = await db.execute(
        select(func.count(Contract.id)).where(
            and_(
                Contract.freelancer_id == freelancer_id,
                Contract.status == ContractStatus.COMPLETED,
            )
        )
    )
    completed_contracts = completed_result.scalar() or 0
    completion_rate = (completed_contracts / total_contracts) * 100

    # 查询自由职业者所有合约的 ID
    contract_ids_result = await db.execute(
        select(Contract.id).where(Contract.freelancer_id == freelancer_id)
    )
    all_contract_ids = [row[0] for row in contract_ids_result.fetchall()]

    # 一次通过率：首次提交（submit_version=1）且验收通过的次数
    first_pass_count = 0
    total_submissions = 0
    if all_contract_ids:
        # 总提交次数（所有验收记录数）
        submission_result = await db.execute(
            select(func.count(AcceptanceRecord.id)).where(
                AcceptanceRecord.contract_id.in_(all_contract_ids)
            )
        )
        total_submissions = submission_result.scalar() or 0

        # 首次验收通过次数（submit_version=1 且结果为 approved）
        first_pass_result = await db.execute(
            select(func.count(AcceptanceRecord.id)).where(
                and_(
                    AcceptanceRecord.contract_id.in_(all_contract_ids),
                    AcceptanceRecord.submit_version == 1,
                    AcceptanceRecord.result == AcceptanceResult.APPROVED,
                )
            )
        )
        first_pass_count = first_pass_result.scalar() or 0

    first_pass_rate = (
        (first_pass_count / total_submissions * 100) if total_submissions > 0 else 100.0
    )

    # 延迟率：未延迟完成次数 / 总完成次数
    # 用合约的 deadline 和 completed 状态来判断
    on_time_count = 0
    if completed_contracts > 0 and all_contract_ids:
        on_time_result = await db.execute(
            select(func.count(Contract.id)).where(
                and_(
                    Contract.freelancer_id == freelancer_id,
                    Contract.status == ContractStatus.COMPLETED,
                    # deadline 为 NULL 或者 updated_at <= deadline 视为按时完成
                    (Contract.deadline.is_(None)) | (Contract.updated_at <= Contract.deadline),
                )
            )
        )
        on_time_count = on_time_result.scalar() or 0

    on_time_rate = (
        (on_time_count / completed_contracts * 100) if completed_contracts > 0 else 100.0
    )

    # 评分：暂时使用默认值
    rating_score = DEFAULT_RATING

    # 加权计算
    weighted_score = (
        first_pass_rate * 0.35
        + on_time_rate * 0.25
        + completion_rate * 0.25
        + rating_score * 0.15
    )

    # 映射到 0-1000：基础分 600 + 加权分映射的增量
    final_score = int(BASE_SCORE + weighted_score * 4)
    final_score = max(0, min(1000, final_score))

    logger.info(
        "freelancer_score_calculated",
        freelancer_id=str(freelancer_id),
        total_contracts=total_contracts,
        completed_contracts=completed_contracts,
        first_pass_rate=round(first_pass_rate, 2),
        on_time_rate=round(on_time_rate, 2),
        completion_rate=round(completion_rate, 2),
        rating_score=rating_score,
        final_score=final_score,
    )

    return final_score


# ============================================================
# 更新信用分
# ============================================================

async def update_credit_score(db: AsyncSession, user_id: uuid.UUID) -> User:
    """
    更新用户信用分
    根据 user_type 调用对应的计算函数，更新 User.credit_score 和 credit_detail
    """
    result = await db.execute(select(User).where(User.id == user_id))
    user = result.scalar_one_or_none()
    if user is None:
        raise ValueError(f"用户不存在: {user_id}")

    # 查询总任务数判断是否为新用户
    if user.user_type == UserType.EMPLOYER:
        count_result = await db.execute(
            select(func.count(Contract.id)).where(Contract.employer_id == user_id)
        )
    else:
        count_result = await db.execute(
            select(func.count(Contract.id)).where(Contract.freelancer_id == user_id)
        )
    total_tasks = count_result.scalar() or 0

    # 冷启动策略：新用户（<5个任务）使用默认分数
    is_new_user = total_tasks < COLD_START_THRESHOLD
    if is_new_user:
        new_score = COLD_START_SCORE
        score_label = "新用户"
    else:
        if user.user_type == UserType.EMPLOYER:
            new_score = await calculate_employer_score(db, user_id)
        else:
            new_score = await calculate_freelancer_score(db, user_id)
        score_label = "已计算"

    # 更新信用详情
    now_str = datetime.now(timezone.utc).isoformat()
    credit_detail = user.credit_detail or {}
    history = credit_detail.get("history", [])

    # 添加历史记录
    history.append({
        "timestamp": now_str,
        "event": "score_update",
        "score_before": user.credit_score,
        "score_after": new_score,
        "reason": f"{score_label}，总任务数: {total_tasks}",
    })

    # 只保留最近 50 条历史记录
    if len(history) > 50:
        history = history[-50:]

    credit_detail["history"] = history
    credit_detail["is_new_user"] = is_new_user

    user.credit_score = new_score
    user.credit_detail = credit_detail
    # 显式标记 JSONB 字段已修改，确保 SQLAlchemy 检测到变更
    flag_modified(user, "credit_detail")
    user.updated_at = datetime.now(timezone.utc)

    await db.commit()
    # 刷新以获取 DB 最新状态（特别对 expire_on_commit=False 的场景）
    await db.refresh(user, attribute_names=["credit_score", "credit_detail", "updated_at"])

    logger.info(
        "credit_score_updated",
        user_id=str(user_id),
        user_type=user.user_type.value,
        new_score=new_score,
        is_new_user=is_new_user,
        total_tasks=total_tasks,
    )

    return user


# ============================================================
# 获取信用历史
# ============================================================

async def get_credit_history(db: AsyncSession, user_id: uuid.UUID) -> dict:
    """
    获取用户信用分历史记录
    返回 credit_detail 中的 history 记录
    """
    result = await db.execute(select(User).where(User.id == user_id))
    user = result.scalar_one_or_none()
    if user is None:
        raise ValueError(f"用户不存在: {user_id}")

    credit_detail = user.credit_detail or {}
    history = credit_detail.get("history", [])

    return {
        "user_id": user.id,
        "credit_score": user.credit_score,
        "history": history,
    }
