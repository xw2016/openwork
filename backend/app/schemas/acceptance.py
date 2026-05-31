"""
验收相关 Pydantic 模型
"""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Optional

from pydantic import BaseModel, Field

from app.models.acceptance import AcceptanceResult


class AcceptanceRequest(BaseModel):
    """验收请求"""
    contract_id: uuid.UUID = Field(..., description="合约ID")
    submit_version: int = Field(..., description="提交版本号")
    acceptance_report: dict = Field(default_factory=dict, description="验收报告")
    result: AcceptanceResult = Field(..., description="验收结果")


class RejectDeliverableRequest(BaseModel):
    """拒绝交付物请求"""
    rejection_reason: str = Field(
        ..., min_length=1, max_length=2000, description="拒绝原因"
    )


class ResubmitDeliverableRequest(BaseModel):
    """重提交付物请求"""
    file_url: str = Field(..., max_length=500, description="新文件URL")
    file_hash: str = Field(..., max_length=128, description="新文件SHA-256哈希")


class AcceptanceRecordResponse(BaseModel):
    """验收记录响应"""
    id: uuid.UUID
    contract_id: uuid.UUID
    submit_version: int
    acceptance_report: dict
    result: AcceptanceResult
    settlement_triggered: bool
    block_hash: Optional[str] = None
    created_at: datetime

    model_config = {"from_attributes": True}
