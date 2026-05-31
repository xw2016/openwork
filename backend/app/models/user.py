"""
用户 ORM 模型
对应 users 表
"""

from __future__ import annotations

import enum
import uuid
from datetime import datetime, timezone
from typing import Optional

from sqlalchemy import DateTime, Enum, Integer, String, Text
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class UserType(str, enum.Enum):
    """用户类型"""
    EMPLOYER = "employer"
    FREELANCER = "freelancer"
    ADMIN = "admin"


class UserStatus(str, enum.Enum):
    """用户状态"""
    ACTIVE = "active"
    DISABLED = "disabled"
    PENDING = "pending"


class User(Base):
    """用户表 ORM 模型"""

    __tablename__ = "users"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    user_type: Mapped[UserType] = mapped_column(
        Enum(UserType, name="user_type_enum", create_constraint=True, values_callable=lambda x: [e.value for e in x]),
        default=UserType.FREELANCER,
        nullable=False,
    )
    nickname: Mapped[str] = mapped_column(String(50), nullable=False)
    avatar: Mapped[Optional[str]] = mapped_column(String(500), nullable=True)
    avatar_url: Mapped[Optional[str]] = mapped_column(String(500), nullable=True)
    phone: Mapped[Optional[str]] = mapped_column(String(20), unique=True, nullable=True, index=True)
    email: Mapped[Optional[str]] = mapped_column(String(100), unique=True, nullable=True, index=True)
    real_name: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    id_card: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    bio: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    domain_tags: Mapped[Optional[list]] = mapped_column(JSONB, nullable=True, default=list)
    verified_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    credit_score: Mapped[int] = mapped_column(Integer, default=600, nullable=False)
    credit_detail: Mapped[dict] = mapped_column(JSONB, default=dict, nullable=False)
    status: Mapped[UserStatus] = mapped_column(
        Enum(UserStatus, name="user_status_enum", create_constraint=True, values_callable=lambda x: [e.value for e in x]),
        default=UserStatus.ACTIVE,
        nullable=False,
        index=True,
    )
    hashed_password: Mapped[str] = mapped_column(String(255), nullable=False)
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
        return f"<User id={self.id} phone={self.phone} type={self.user_type}>"
