"""
用户相关 Pydantic 模型
"""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Optional

from pydantic import BaseModel, Field

from app.models.user import UserStatus, UserType


class UserRegisterRequest(BaseModel):
    """用户注册请求"""
    phone: str = Field(..., min_length=11, max_length=20, description="手机号")
    password: str = Field(..., min_length=6, max_length=128, description="密码")
    nickname: str = Field(..., min_length=1, max_length=50, description="昵称")
    user_type: UserType = Field(UserType.FREELANCER, description="用户类型")


class UserLoginRequest(BaseModel):
    """用户登录请求"""
    phone: str = Field(..., description="手机号")
    password: str = Field(..., description="密码")


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
    phone: str
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
