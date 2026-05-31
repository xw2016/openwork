"""
资金托管与结算服务
处理托管资金的创建、释放、退款等核心业务逻辑
"""

from __future__ import annotations

from decimal import Decimal
from typing import List, Optional
from uuid import UUID

import structlog
from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.contract import Contract, ContractStatus
from app.models.transaction import Transaction, TransactionStatus, TransactionType

logger = structlog.get_logger("modules.payment.service")


# ============================================================
# 2.16 资金托管流程
# ============================================================


async def create_escrow(
    db: AsyncSession,
    contract_id: UUID,
    employer_id: UUID,
    amount: Decimal,
) -> Transaction:
    """
    创建资金托管（雇主预付资金 -> 冻结）

    校验逻辑：
    - 合约存在
    - 金额匹配（base_amount + bonus_amount）
    - 当前用户是合约的雇主

    返回创建的 escrow 类型交易，status=pending
    """
    # 查询合约
    result = await db.execute(select(Contract).where(Contract.id == contract_id))
    contract = result.scalar_one_or_none()
    if contract is None:
        raise ValueError("合约不存在")

    # 校验当前用户是否为合约雇主
    if contract.employer_id != employer_id:
        raise ValueError("只有合约的雇主可以创建资金托管")

    # 检查是否已有待处理的托管，防止重复创建
    existing = await db.execute(
        select(Transaction).where(
            Transaction.contract_id == contract_id,
            Transaction.transaction_type == TransactionType.ESCROW,
            Transaction.status == TransactionStatus.PENDING,
        )
    )
    if existing.scalar_one_or_none() is not None:
        raise ValueError("该合约已有待处理的资金托管，不能重复创建")

    # 校验金额匹配：雇主应支付 base_amount + bonus_amount
    expected_amount = contract.base_amount + contract.bonus_amount
    if amount != expected_amount:
        raise ValueError(
            f"托管金额不匹配：期望 {expected_amount}，实际 {amount}"
        )

    # 创建 escrow 交易记录
    escrow = Transaction(
        contract_id=contract_id,
        transaction_type=TransactionType.ESCROW,
        amount=amount,
        from_user_id=employer_id,
        to_user_id=None,  # 资金冻结，暂无收款方
        commission=Decimal("0.00"),
        status=TransactionStatus.PENDING,
    )
    db.add(escrow)
    await db.commit()
    await db.refresh(escrow)

    logger.info(
        "escrow_created",
        transaction_id=str(escrow.id),
        contract_id=str(contract_id),
        employer_id=str(employer_id),
        amount=str(amount),
    )
    return escrow


# ============================================================
# 2.17 自动结算
# ============================================================


async def release_escrow(
    db: AsyncSession,
    contract_id: UUID,
) -> Transaction:
    """
    验收通过后释放资金给自由职业者

    金额计算规则：
    - 雇主实际支付 = base_amount + bonus_amount
    - 佣金 = (base_amount + bonus_amount) * commission_rate
    - 自由职业者实收 = (base_amount + bonus_amount) - commission

    创建 payment 类型交易，佣金记录在 commission 字段
    """
    # 查询合约
    result = await db.execute(select(Contract).where(Contract.id == contract_id))
    contract = result.scalar_one_or_none()
    if contract is None:
        raise ValueError("合约不存在")

    # 校验合约必须有自由职业者
    if contract.freelancer_id is None:
        raise ValueError("合约尚未分配自由职业者，无法释放资金")

    # 查找对应的 escrow 交易且状态为 pending
    escrow_result = await db.execute(
        select(Transaction).where(
            Transaction.contract_id == contract_id,
            Transaction.transaction_type == TransactionType.ESCROW,
            Transaction.status == TransactionStatus.PENDING,
        )
    )
    escrow = escrow_result.scalar_one_or_none()
    if escrow is None:
        raise ValueError("未找到有效的托管交易（pending 状态的 escrow）")

    # 计算金额
    total_amount = contract.base_amount + contract.bonus_amount
    commission = total_amount * contract.commission_rate

    # 标记 escrow 为已完成
    escrow.status = TransactionStatus.COMPLETED

    # 创建 payment 交易（释放资金给自由职业者）
    payment = Transaction(
        contract_id=contract_id,
        transaction_type=TransactionType.PAYMENT,
        amount=total_amount,
        from_user_id=contract.employer_id,
        to_user_id=contract.freelancer_id,
        commission=commission,
        status=TransactionStatus.COMPLETED,
    )
    db.add(payment)
    await db.commit()
    await db.refresh(payment)

    logger.info(
        "escrow_released",
        payment_id=str(payment.id),
        contract_id=str(contract_id),
        amount=str(total_amount),
        commission=str(commission),
        freelancer_id=str(contract.freelancer_id),
    )
    return payment


# ============================================================
# 2.18 退款与终止
# ============================================================


async def refund_escrow(
    db: AsyncSession,
    contract_id: UUID,
    reason: str = "",
) -> Transaction:
    """
    合约终止时退还雇主预付资金

    校验逻辑：
    - 原 escrow 交易存在且状态为 pending 或 completed
    - 创建 refund 类型交易
    """
    # 查询合约
    result = await db.execute(select(Contract).where(Contract.id == contract_id))
    contract = result.scalar_one_or_none()
    if contract is None:
        raise ValueError("合约不存在")

    # 查找对应的 escrow 交易，状态为 pending 或 completed
    escrow_result = await db.execute(
        select(Transaction).where(
            Transaction.contract_id == contract_id,
            Transaction.transaction_type == TransactionType.ESCROW,
            Transaction.status.in_([
                TransactionStatus.PENDING,
                TransactionStatus.COMPLETED,
            ]),
        )
    )
    escrow = escrow_result.scalar_one_or_none()
    if escrow is None:
        raise ValueError("未找到有效的托管交易（pending 或 completed 状态的 escrow）")

    # 取消原 escrow 交易
    escrow.status = TransactionStatus.CANCELLED

    # 创建 refund 交易（退还雇主）
    refund = Transaction(
        contract_id=contract_id,
        transaction_type=TransactionType.REFUND,
        amount=escrow.amount,
        from_user_id=None,  # 资金从平台退回
        to_user_id=contract.employer_id,
        commission=Decimal("0.00"),
        status=TransactionStatus.COMPLETED,
    )
    db.add(refund)
    await db.commit()
    await db.refresh(refund)

    logger.info(
        "escrow_refunded",
        refund_id=str(refund.id),
        contract_id=str(contract_id),
        amount=str(escrow.amount),
        employer_id=str(contract.employer_id),
        reason=reason,
    )
    return refund


# ============================================================
# 交易记录查询
# ============================================================


async def list_transactions(
    db: AsyncSession,
    contract_id: UUID,
    page: int = 1,
    size: int = 20,
) -> dict:
    """
    分页查询合约的交易记录
    """
    # 总数查询
    count_query = select(func.count(Transaction.id)).where(
        Transaction.contract_id == contract_id
    )
    total_result = await db.execute(count_query)
    total = total_result.scalar() or 0

    # 分页查询
    offset = (page - 1) * size
    query = (
        select(Transaction)
        .where(Transaction.contract_id == contract_id)
        .order_by(Transaction.created_at.desc())
        .offset(offset)
        .limit(size)
    )
    result = await db.execute(query)
    transactions = list(result.scalars().all())

    total_pages = (total + size - 1) // size if total > 0 else 0

    return {
        "items": transactions,
        "total": total,
        "page": page,
        "page_size": size,
        "total_pages": total_pages,
    }
