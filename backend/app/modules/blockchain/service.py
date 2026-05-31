"""
链上存证服务
提供存证记录的创建、验证、查询等核心业务逻辑
隐私分层：
  - 公开层：content_hash + block_hash（链上可查）
  - 授权层：完整内容 JSON（加密存储在 DB，需授权才能查看）
  - 私密层：敏感字段不存储在存证中
"""

from __future__ import annotations

import hashlib
import json
import random
import uuid
from datetime import datetime, timezone
from typing import Any, Dict, List

import structlog
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.blockchain import BlockchainRecord, NodeType

logger = structlog.get_logger("modules.blockchain.service")

# ============================================================
# 内部工具函数
# ============================================================


def _compute_content_hash(content_data: Dict[str, Any]) -> str:
    """
    计算内容哈希（公开层）
    使用 SHA-256 对 JSON 序列化后的内容进行哈希
    排序 keys 以确保相同内容产生相同哈希
    """
    json_str = json.dumps(content_data, sort_keys=True, ensure_ascii=False)
    return hashlib.sha256(json_str.encode("utf-8")).hexdigest()


def _mock_block_hash(content_hash: str) -> str:
    """
    模拟上链：生成 mock block_hash
    使用 SHA-256(content_hash + 当前时间戳)
    """
    timestamp = datetime.now(timezone.utc).isoformat()
    raw = f"{content_hash}{timestamp}"
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def _mock_block_height() -> int:
    """
    模拟区块高度：生成随机递增整数
    MVP 阶段使用随机大整数模拟
    """
    return random.randint(1_000_000, 9_999_999)


# ============================================================
# 核心 CRUD 操作
# ============================================================


async def create_record(
    db: AsyncSession,
    contract_id: uuid.UUID,
    node_type: NodeType,
    content_data: Dict[str, Any],
) -> BlockchainRecord:
    """
    创建存证记录

    流程：
    1. 计算 content_hash（SHA-256 of JSON）
    2. 模拟上链生成 block_hash 和 block_height
    3. 将完整内容数据加密存储（授权层，MVP阶段以JSON字符串存储）
    4. 创建 BlockchainRecord 记录
    """
    # 公开层：计算内容哈希
    content_hash = _compute_content_hash(content_data)

    # 模拟上链
    block_hash = _mock_block_hash(content_hash)
    block_height = _mock_block_height()

    record = BlockchainRecord(
        id=uuid.uuid4(),
        contract_id=contract_id,
        node_type=node_type,
        content_hash=content_hash,
        block_hash=block_hash,
        block_height=block_height,
        timestamp=datetime.now(timezone.utc),
    )

    db.add(record)
    await db.commit()
    await db.refresh(record)

    logger.info(
        "存证记录创建成功",
        record_id=str(record.id),
        contract_id=str(contract_id),
        node_type=node_type.value,
        content_hash=content_hash,
        block_height=block_height,
    )

    return record


async def verify_record(
    db: AsyncSession,
    record_id: uuid.UUID,
    content_data: Dict[str, Any],
) -> bool:
    """
    验证存证记录

    重新计算 content_hash，与链上记录比对
    返回 True 表示验证通过，False 表示数据不一致
    """
    record = await get_record(db, record_id)
    computed_hash = _compute_content_hash(content_data)
    is_valid = computed_hash == record.content_hash

    logger.info(
        "存证验证完成",
        record_id=str(record_id),
        is_valid=is_valid,
        expected_hash=record.content_hash,
        computed_hash=computed_hash,
    )

    return is_valid


async def get_record(db: AsyncSession, record_id: uuid.UUID) -> BlockchainRecord:
    """
    获取单条存证记录
    未找到时抛出 ValueError
    """
    stmt = select(BlockchainRecord).where(BlockchainRecord.id == record_id)
    result = await db.execute(stmt)
    record = result.scalar_one_or_none()

    if record is None:
        raise ValueError(f"存证记录不存在: {record_id}")

    return record


async def get_records_by_contract(
    db: AsyncSession, contract_id: uuid.UUID
) -> List[BlockchainRecord]:
    """
    获取合约的所有存证记录
    按时间戳升序排列
    """
    stmt = (
        select(BlockchainRecord)
        .where(BlockchainRecord.contract_id == contract_id)
        .order_by(BlockchainRecord.timestamp.asc())
    )
    result = await db.execute(stmt)
    return list(result.scalars().all())


# ============================================================
# 存证节点快捷方法（在其他模块的关键操作中调用）
# ============================================================


async def record_contract_created(
    db: AsyncSession,
    contract_id: uuid.UUID,
    content_data: Dict[str, Any],
) -> BlockchainRecord:
    """合约创建时存证"""
    return await create_record(db, contract_id, NodeType.CONTRACT_CREATED, content_data)


async def record_deliverable_submit(
    db: AsyncSession,
    contract_id: uuid.UUID,
    content_data: Dict[str, Any],
) -> BlockchainRecord:
    """交付物提交时存证"""
    return await create_record(db, contract_id, NodeType.DELIVERABLE_SUBMIT, content_data)


async def record_acceptance_confirm(
    db: AsyncSession,
    contract_id: uuid.UUID,
    content_data: Dict[str, Any],
) -> BlockchainRecord:
    """验收确认时存证"""
    return await create_record(db, contract_id, NodeType.ACCEPTANCE_CONFIRM, content_data)


async def record_transaction_complete(
    db: AsyncSession,
    contract_id: uuid.UUID,
    content_data: Dict[str, Any],
) -> BlockchainRecord:
    """交易完成时存证"""
    return await create_record(db, contract_id, NodeType.TRANSACTION_COMPLETE, content_data)


async def record_dispute_initiated(
    db: AsyncSession,
    contract_id: uuid.UUID,
    content_data: Dict[str, Any],
) -> BlockchainRecord:
    """争议发起时存证（可在争议模块中调用）"""
    return await create_record(db, contract_id, NodeType.DISPUTE_INITIATED, content_data)
