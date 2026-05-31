"""
用户相关 Pydantic 模型
包含注册、登录、令牌、用户信息等请求/响应模型
"""

from __future__ import annotations

import re
import uuid
from datetime import datetime
from typing import List, Optional

from pydantic import BaseModel, Field, field_validator

from app.models.user import UserStatus, UserType


# ============================================================
# 密码强度校验正则
# - 至少8位
# - 包含大写字母、小写字母、数字中的至少两种
# ============================================================
_PASSWORD_PATTERN = re.compile(
    r"^(?:(?=.*[a-z])(?=.*[A-Z])|(?=.*[a-z])(?=.*\d)|(?=.*[A-Z])(?=.*\d)).{8,128}$"
)

# 中国大陆手机号正则
_PHONE_PATTERN = re.compile(r"^1[3-9]\d{9}$")

# 邮箱正则
_EMAIL_PATTERN = re.compile(r"^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$")


def _validate_password_strength(v: str) -> str:
    """校验密码强度：至少8位，包含大写/小写/数字中的至少两种"""
    if not _PASSWORD_PATTERN.match(v):
        raise ValueError("密码必须为8-128位，且包含大写字母、小写字母、数字中的至少两种")
    return v


def _validate_phone_format(v: str) -> str:
    """校验中国大陆手机号格式"""
    if not _PHONE_PATTERN.match(v):
        raise ValueError("手机号格式不正确，需为11位中国大陆手机号")
    return v


def _validate_email_format(v: str) -> str:
    """校验邮箱格式"""
    if not _EMAIL_PATTERN.match(v):
        raise ValueError("邮箱格式不正确")
    return v


class UserRegisterRequest(BaseModel):
    """
    用户注册请求（手机号注册）
    phone 改为可选，支持手机号或邮箱注册
    至少需要提供 phone 或 email 之一
    """
    phone: Optional[str] = Field(None, min_length=11, max_length=20, description="手机号（可选）")
    email: Optional[str] = Field(None, max_length=100, description="邮箱（可选）")
    password: str = Field(..., min_length=8, max_length=128, description="密码")
    nickname: str = Field(..., min_length=1, max_length=50, description="昵称")
    user_type: UserType = Field(UserType.FREELANCER, description="用户类型")

    @field_validator("phone", mode="before")
    @classmethod
    def validate_phone(cls, v: Optional[str]) -> Optional[str]:
        """校验手机号格式（如果提供了手机号）"""
        if v is not None and v.strip():
            v = v.strip()
            _validate_phone_format(v)
            return v
        return v

    @field_validator("email", mode="before")
    @classmethod
    def validate_email(cls, v: Optional[str]) -> Optional[str]:
        """校验邮箱格式（如果提供了邮箱）"""
        if v is not None and v.strip():
            v = v.strip().lower()
            _validate_email_format(v)
            return v
        return v

    @field_validator("password", mode="before")
    @classmethod
    def validate_password(cls, v: str) -> str:
        """校验密码强度"""
        return _validate_password_strength(v)

    def model_post_init(self, __context) -> None:
        """确保至少提供了 phone 或 email 之一"""
        if not self.phone and not self.email:
            raise ValueError("手机号和邮箱至少需要提供一个")


class UserEmailRegisterRequest(BaseModel):
    """
    邮箱注册请求（独立端点使用）
    """
    email: str = Field(..., max_length=100, description="邮箱地址")
    password: str = Field(..., min_length=8, max_length=128, description="密码")
    nickname: str = Field(..., min_length=1, max_length=50, description="昵称")
    user_type: UserType = Field(UserType.FREELANCER, description="用户类型")

    @field_validator("email", mode="before")
    @classmethod
    def validate_email(cls, v: str) -> str:
        """校验邮箱格式"""
        v = v.strip().lower()
        _validate_email_format(v)
        return v

    @field_validator("password", mode="before")
    @classmethod
    def validate_password(cls, v: str) -> str:
        """校验密码强度"""
        return _validate_password_strength(v)


class UserLoginRequest(BaseModel):
    """
    用户登录请求
    支持手机号或邮箱登录
    """
    phone: Optional[str] = Field(None, description="手机号（与email二选一）")
    email: Optional[str] = Field(None, description="邮箱（与phone二选一）")
    password: str = Field(..., description="密码")

    def model_post_init(self, __context) -> None:
        """确保至少提供了 phone 或 email 之一"""
        if not self.phone and not self.email:
            raise ValueError("手机号和邮箱至少需要提供一个")


class TokenResponse(BaseModel):
    """JWT 令牌响应"""
    access_token: str = Field(description="访问令牌")
    refresh_token: str = Field(description="刷新令牌")
    token_type: str = Field("bearer", description="令牌类型")
    expires_in: int = Field(description="过期时间（秒）")


class RefreshTokenRequest(BaseModel):
    """刷新令牌请求"""
    refresh_token: str = Field(..., description="刷新令牌")


class UserInfoResponse(BaseModel):
    """用户信息响应"""
    id: uuid.UUID
    user_type: UserType
    nickname: str
    avatar: Optional[str] = None
    phone: Optional[str] = None
    email: Optional[str] = None
    credit_score: int
    status: UserStatus
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class UserUpdateRequest(BaseModel):
    """用户更新请求"""
    nickname: Optional[str] = Field(None, max_length=50)
    avatar: Optional[str] = Field(None, max_length=500)
    email: Optional[str] = Field(None, max_length=100)
    real_name: Optional[str] = Field(None, max_length=255)
    id_card: Optional[str] = Field(None, max_length=255)


class LoginLogResponse(BaseModel):
    """登录日志响应"""
    user_id: str = Field(description="用户ID")
    login_type: str = Field(description="登录方式（phone/email）")
    identifier: str = Field(description="登录标识（手机号或邮箱）")
    ip: str = Field(description="客户端IP")
    user_agent: str = Field(description="设备信息/User-Agent")
    success: bool = Field(description="是否登录成功")
    failure_reason: Optional[str] = Field(None, description="失败原因")
    login_time: datetime = Field(description="登录时间")


# ============================================================
# 用户资料相关模型（profile 模块使用）
# ============================================================

class ProfileResponse(BaseModel):
    """用户公开资料响应"""
    id: uuid.UUID
    user_type: UserType
    nickname: str
    avatar: Optional[str] = None
    bio: Optional[str] = None
    domain_tags: Optional[List[str]] = None
    credit_score: int
    status: UserStatus
    created_at: datetime

    model_config = {"from_attributes": True}


class ProfileUpdateRequest(BaseModel):
    """更新用户资料请求"""
    nickname: Optional[str] = Field(None, max_length=50, description="昵称")
    avatar: Optional[str] = Field(None, max_length=500, description="头像URL")
    bio: Optional[str] = Field(None, max_length=500, description="个人简介")
    domain_tags: Optional[List[str]] = Field(None, description="领域标签")


class AvatarUploadRequest(BaseModel):
    """头像上传请求"""
    avatar_data: str = Field(..., description="头像数据（base64编码或URL）")
    avatar_type: str = Field("url", description="数据类型: url 或 base64")


class VerifyRequest(BaseModel):
    """实名认证请求"""
    real_name: str = Field(..., min_length=2, max_length=50, description="真实姓名")
    id_card: str = Field(..., min_length=15, max_length=18, description="身份证号")


class UserStatsResponse(BaseModel):
    """用户统计数据响应"""
    total_contracts: int = Field(0, description="总合约数")
    completed_contracts: int = Field(0, description="已完成合约数")
    total_earnings: float = Field(0.0, description="总收入")
    average_rating: float = Field(0.0, description="平均评分")
