"""
合约 ORM 模型
对应 contracts 表
"""

from __future__ import annotations

import enum
import uuid
from datetime import datetime, timezone
from decimal import Decimal
from typing import Optional

from sqlalchemy import DateTime, Enum, Integer, Numeric, String
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class TaskType(str, enum.Enum):
    """任务类型"""
    DEVELOPMENT = "development"
    DESIGN = "design"
    COPYWRITING = "copywriting"
    TRANSLATION = "translation"
    DATA_LABELING = "data_labeling"
    CONSULTING = "consulting"
    OTHER = "other"


class ContractStatus(str, enum.Enum):
    """合约状态"""
    DRAFT = "draft"
    PENDING = "pending"
    IN_PROGRESS = "in_progress"
    REVIEW = "review"
    COMPLETED = "completed"
    TERMINATED = "terminated"
    DISPUTED = "disputed"


class Contract(Base):
    """任务合约表 ORM 模型"""

    __tablename__ = "contracts"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    contract_no: Mapped[str] = mapped_column(
        String(50), unique=True, nullable=False, index=True
    )
    employer_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), nullable=False, index=True
    )
    freelancer_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True), nullable=True, index=True
    )
    title: Mapped[str] = mapped_column(String(200), nullable=False)
    task_type: Mapped[TaskType] = mapped_column(
        Enum(TaskType, name="task_type_enum", create_constraint=True, values_callable=lambda x: [e.value for e in x]),
        nullable=False,
    )
    intent_blueprint: Mapped[dict] = mapped_column(JSONB, default=dict, nullable=False)
    deliverables: Mapped[list] = mapped_column(JSONB, default=list, nullable=False)
    base_amount: Mapped[Decimal] = mapped_column(
        Numeric(12, 2), default=Decimal("0.00"), nullable=False
    )
    bonus_amount: Mapped[Decimal] = mapped_column(
        Numeric(12, 2), default=Decimal("0.00"), nullable=False
    )
    bonus_condition: Mapped[Optional[dict]] = mapped_column(JSONB, nullable=True)
    tracking_period: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    commission_rate: Mapped[Decimal] = mapped_column(
        Numeric(5, 4), default=Decimal("0.0500"), nullable=False
    )
    deadline: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    version: Mapped[int] = mapped_column(Integer, default=1, nullable=False)
    status: Mapped[ContractStatus] = mapped_column(
        Enum(ContractStatus, name="contract_status_enum", create_constraint=True, values_callable=lambda x: [e.value for e in x]),
        default=ContractStatus.DRAFT,
        nullable=False,
        index=True,
    )
    block_hash: Mapped[Optional[str]] = mapped_column(String(128), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        nullable=False,
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
        nullable=False,
    )

    def __repr__(self) -> str:
        return f"<Contract id={self.id} no={self.contract_no} status={self.status}>"
