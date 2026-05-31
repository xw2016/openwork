"""
合约相关 Pydantic 模型
"""

from __future__ import annotations

import uuid
from datetime import datetime
from decimal import Decimal
from typing import Any, List, Optional

from pydantic import BaseModel, Field

from app.models.contract import ContractStatus, TaskType


class ContractCreateRequest(BaseModel):
    """创建合约请求"""
    title: str = Field(..., min_length=1, max_length=200, description="任务标题")
    task_type: TaskType = Field(..., description="任务类型")
    intent_blueprint: dict = Field(default_factory=dict, description="意图蓝图")
    deliverables: List[dict] = Field(default_factory=list, description="预期交付物")
    base_amount: Decimal = Field(..., ge=0, description="基础金额（元）")
    bonus_amount: Decimal = Field(Decimal("0.00"), ge=0, description="奖金金额（元）")
    bonus_condition: Optional[dict] = Field(None, description="奖金触发条件")
    tracking_period: Optional[int] = Field(None, ge=0, description="跟踪期（天）")
    deadline: Optional[datetime] = Field(None, description="截止时间")


class ContractUpdateRequest(BaseModel):
    """更新合约请求"""
    title: Optional[str] = Field(None, max_length=200)
    intent_blueprint: Optional[dict] = None
    deliverables: Optional[List[dict]] = None
    base_amount: Optional[Decimal] = Field(None, ge=0)
    bonus_amount: Optional[Decimal] = Field(None, ge=0)
    bonus_condition: Optional[dict] = None
    deadline: Optional[datetime] = None


class ContractResponse(BaseModel):
    """合约响应"""
    id: uuid.UUID
    contract_no: str
    employer_id: uuid.UUID
    freelancer_id: Optional[uuid.UUID] = None
    title: str
    task_type: TaskType
    intent_blueprint: dict
    deliverables: list
    base_amount: Decimal
    bonus_amount: Decimal
    bonus_condition: Optional[dict] = None
    tracking_period: Optional[int] = None
    commission_rate: Decimal
    deadline: Optional[datetime] = None
    version: int
    status: ContractStatus
    block_hash: Optional[str] = None
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}
