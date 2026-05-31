"""
交付物 ORM 模型
对应 deliverables 表
"""

from __future__ import annotations

import enum
import uuid
from datetime import datetime, timezone
from typing import Optional

from sqlalchemy import DateTime, Enum, Integer, String
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class AcceptanceStatus(str, enum.Enum):
    """交付物验收状态"""
    NOT_SUBMITTED = "not_submitted"
    PENDING = "pending"
    APPROVED = "approved"
    REJECTED = "rejected"


class Deliverable(Base):
    """交付物表 ORM 模型"""

    __tablename__ = "deliverables"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    contract_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), nullable=False, index=True
    )
    deliverable_index: Mapped[int] = mapped_column(Integer, default=1, nullable=False)
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    required_format: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    acceptance_criteria: Mapped[dict] = mapped_column(JSONB, default=dict, nullable=False)
    file_url: Mapped[Optional[str]] = mapped_column(String(500), nullable=True)
    file_hash: Mapped[Optional[str]] = mapped_column(String(128), nullable=True)
    submit_version: Mapped[int] = mapped_column(Integer, default=1, nullable=False)
    submit_time: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    acceptance_result: Mapped[Optional[dict]] = mapped_column(JSONB, nullable=True)
    acceptance_status: Mapped[AcceptanceStatus] = mapped_column(
        Enum(AcceptanceStatus, name="acceptance_status_enum", create_constraint=True),
        default=AcceptanceStatus.NOT_SUBMITTED,
        nullable=False,
        index=True,
    )
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
        return f"<Deliverable id={self.id} name={self.name} status={self.acceptance_status}>"
