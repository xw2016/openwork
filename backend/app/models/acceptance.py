"""
验收记录 ORM 模型
对应 acceptance_records 表
"""

from __future__ import annotations

import enum
import uuid
from datetime import datetime, timezone

from sqlalchemy import Boolean, DateTime, Enum, Integer, String
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class AcceptanceResult(str, enum.Enum):
    """验收结果"""
    APPROVED = "approved"
    REJECTED = "rejected"


class AcceptanceRecord(Base):
    """验收记录表 ORM 模型"""

    __tablename__ = "acceptance_records"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    contract_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), nullable=False, index=True
    )
    submit_version: Mapped[int] = mapped_column(Integer, nullable=False)
    acceptance_report: Mapped[dict] = mapped_column(JSONB, default=dict, nullable=False)
    result: Mapped[AcceptanceResult] = mapped_column(
        Enum(AcceptanceResult, name="acceptance_result_enum", create_constraint=True, values_callable=lambda x: [e.value for e in x]),
        nullable=False,
    )
    settlement_triggered: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    block_hash: Mapped[str | None] = mapped_column(String(128), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        nullable=False,
    )

    def __repr__(self) -> str:
        return f"<AcceptanceRecord id={self.id} result={self.result}>"
