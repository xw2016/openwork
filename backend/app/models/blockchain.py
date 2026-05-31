"""
链上存证 ORM 模型
对应 blockchain_records 表
"""

from __future__ import annotations

import enum
import uuid
from datetime import datetime, timezone
from typing import Optional

from sqlalchemy import BigInteger, DateTime, Enum, String
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class NodeType(str, enum.Enum):
    """存证节点类型"""
    CONTRACT_CREATED = "contract_created"
    DELIVERABLE_SUBMIT = "deliverable_submit"
    ACCEPTANCE_CONFIRM = "acceptance_confirm"
    TRANSACTION_COMPLETE = "transaction_complete"
    DISPUTE_INITIATED = "dispute_initiated"


class BlockchainRecord(Base):
    """链上存证表 ORM 模型"""

    __tablename__ = "blockchain_records"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    contract_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), nullable=False, index=True
    )
    node_type: Mapped[NodeType] = mapped_column(
        Enum(NodeType, name="node_type_enum", create_constraint=True),
        nullable=False,
        index=True,
    )
    content_hash: Mapped[str] = mapped_column(String(128), nullable=False)
    block_hash: Mapped[str] = mapped_column(String(128), nullable=False, index=True)
    block_height: Mapped[Optional[int]] = mapped_column(BigInteger, nullable=True)
    timestamp: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        nullable=False,
    )

    def __repr__(self) -> str:
        return f"<BlockchainRecord id={self.id} type={self.node_type}>"
