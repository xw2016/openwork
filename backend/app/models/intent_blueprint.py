"""
意图蓝图 ORM 模型
对应 intent_blueprints 表
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


class BlueprintStatus(str, enum.Enum):
    """蓝图状态"""
    DRAFT = "draft"       # 草稿，可编辑
    LOCKED = "locked"     # 已锁定，不可修改
    ARCHIVED = "archived" # 已归档


class IntentBlueprint(Base):
    """意图蓝图表 ORM 模型"""

    __tablename__ = "intent_blueprints"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), nullable=False, index=True
    )
    title: Mapped[str] = mapped_column(String(200), nullable=False)
    task_type: Mapped[str] = mapped_column(String(50), nullable=False)
    content: Mapped[dict] = mapped_column(JSONB, default=dict, nullable=False)
    status: Mapped[BlueprintStatus] = mapped_column(
        Enum(BlueprintStatus, name="blueprint_status_enum", create_constraint=True, values_callable=lambda x: [e.value for e in x]),
        default=BlueprintStatus.DRAFT,
        nullable=False,
        index=True,
    )
    version: Mapped[int] = mapped_column(Integer, default=1, nullable=False)
    locked_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True), nullable=True
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
        return f"<IntentBlueprint id={self.id} title={self.title} status={self.status}>"
