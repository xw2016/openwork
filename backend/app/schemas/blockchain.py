"""
存证相关 Pydantic 模型
"""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field

from app.models.blockchain import NodeType


class BlockchainRecordCreateRequest(BaseModel):
    """创建存证请求"""
    contract_id: uuid.UUID = Field(..., description="合约ID")
    node_type: NodeType = Field(..., description="存证节点类型")
    content_data: Dict[str, Any] = Field(..., description="存证内容数据")


class BlockchainVerifyBody(BaseModel):
    """验证存证请求体"""
    content_data: Dict[str, Any] = Field(..., description="待验证的内容数据")


class BlockchainRecordResponse(BaseModel):
    """链上存证记录响应"""
    id: uuid.UUID
    contract_id: uuid.UUID
    node_type: NodeType
    content_hash: str
    block_hash: str
    block_height: Optional[int] = None
    timestamp: datetime

    model_config = {"from_attributes": True}


class BlockchainVerifyRequest(BaseModel):
    """链上验证请求"""
    contract_id: uuid.UUID = Field(..., description="合约ID")
    content_hash: str = Field(..., description="待验证的内容哈希")
