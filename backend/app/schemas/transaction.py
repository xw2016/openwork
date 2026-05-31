"""
交易相关 Pydantic 模型
"""

from __future__ import annotations

import uuid
from datetime import datetime
from decimal import Decimal
from typing import Optional

from pydantic import BaseModel, Field

from app.models.transaction import TransactionStatus, TransactionType


class TransactionCreateRequest(BaseModel):
    """创建交易请求"""
    contract_id: uuid.UUID = Field(..., description="关联合约ID")
    transaction_type: TransactionType = Field(..., description="交易类型")
    amount: Decimal = Field(..., gt=0, description="交易金额（元）")
    from_user_id: Optional[uuid.UUID] = Field(None, description="付款方ID")
    to_user_id: Optional[uuid.UUID] = Field(None, description="收款方ID")


class TransactionResponse(BaseModel):
    """交易记录响应"""
    id: uuid.UUID
    contract_id: uuid.UUID
    transaction_type: TransactionType
    amount: Decimal
    from_user_id: Optional[uuid.UUID] = None
    to_user_id: Optional[uuid.UUID] = None
    commission: Decimal
    status: TransactionStatus
    block_hash: Optional[str] = None
    created_at: datetime

    model_config = {"from_attributes": True}
