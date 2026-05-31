"""
交付物相关 Pydantic 模型
"""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Optional

from pydantic import BaseModel, Field

from app.models.deliverable import AcceptanceStatus


class DeliverableCreateRequest(BaseModel):
    """创建交付物请求"""
    contract_id: uuid.UUID = Field(..., description="所属合约ID")
    deliverable_index: int = Field(1, ge=1, description="交付物序号")
    name: str = Field(..., min_length=1, max_length=200, description="交付物名称")
    required_format: Optional[str] = Field(None, max_length=100, description="要求格式")
    acceptance_criteria: dict = Field(default_factory=dict, description="验收标准")


class DeliverableSubmitRequest(BaseModel):
    """提交交付物请求"""
    file_url: str = Field(..., max_length=500, description="文件URL")
    file_hash: Optional[str] = Field(None, max_length=128, description="文件SHA-256哈希")


class DeliverableResponse(BaseModel):
    """交付物响应"""
    id: uuid.UUID
    contract_id: uuid.UUID
    deliverable_index: int
    name: str
    required_format: Optional[str] = None
    acceptance_criteria: dict
    file_url: Optional[str] = None
    file_hash: Optional[str] = None
    submit_version: int
    submit_time: Optional[datetime] = None
    acceptance_result: Optional[dict] = None
    acceptance_status: AcceptanceStatus
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}
