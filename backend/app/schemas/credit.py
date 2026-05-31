"""
信用评分相关 Pydantic 模型
"""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field


class CreditScoreResponse(BaseModel):
    """信用分响应"""
    user_id: uuid.UUID = Field(description="用户ID")
    credit_score: int = Field(description="信用分（0-1000）")
    credit_level: str = Field(description="信用等级")
    is_new_user: bool = Field(description="是否为新用户（冷启动）")
    detail: Optional[Dict[str, Any]] = Field(None, description="信用详情")


class CreditHistoryItem(BaseModel):
    """信用历史记录项"""
    timestamp: str = Field(description="记录时间")
    event: str = Field(description="事件类型")
    score_before: int = Field(description="变更前分数")
    score_after: int = Field(description="变更后分数")
    reason: str = Field(description="变更原因")


class CreditHistoryResponse(BaseModel):
    """信用历史响应"""
    user_id: uuid.UUID = Field(description="用户ID")
    credit_score: int = Field(description="当前信用分")
    history: List[CreditHistoryItem] = Field(default_factory=list, description="历史记录")
