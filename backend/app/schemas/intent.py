"""
意图建模模块 Pydantic 模型
包括：意图分析请求/响应、蓝图 CRUD 请求/响应、追问相关模型
"""

from __future__ import annotations

import uuid
from datetime import datetime
from enum import Enum
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field


# ============================================================
# 枚举
# ============================================================

class TaskType(str, Enum):
    """任务类型（与 Contract 模型保持一致）"""
    DEVELOPMENT = "development"
    DESIGN = "design"
    COPYWRITING = "copywriting"
    TRANSLATION = "translation"
    DATA_LABELING = "data_labeling"
    CONSULTING = "consulting"
    OTHER = "other"


class QuestionPriority(str, Enum):
    """追问优先级"""
    REQUIRED = "required"    # 必答
    IMPORTANT = "important"  # 重要
    OPTIONAL = "optional"    # 可选


# ============================================================
# 意图分析
# ============================================================

class IntentAnalyzeRequest(BaseModel):
    """意图分析请求"""
    user_input: str = Field(
        ..., min_length=1, max_length=2000, description="用户自然语言输入"
    )
    context: Optional[Dict[str, Any]] = Field(
        default_factory=dict, description="上下文信息（行业、预算范围等）"
    )


class IntentAnalysisData(BaseModel):
    """意图分析结果数据"""
    task_type: str = Field(description="推断的任务类型")
    summary: str = Field(description="意图摘要")
    keywords: List[str] = Field(description="关键词列表")
    confidence: float = Field(description="置信度 0-1")
    raw_input: str = Field(description="原始输入")


class IntentAnalyzeResponse(BaseModel):
    """意图分析响应"""
    analysis: IntentAnalysisData = Field(description="意图分析结果")


# ============================================================
# 蓝图 CRUD
# ============================================================

class BlueprintCreateRequest(BaseModel):
    """创建蓝图请求"""
    title: str = Field(..., min_length=1, max_length=200, description="蓝图标题")
    task_type: TaskType = Field(..., description="任务类型")
    content: Dict[str, Any] = Field(
        default_factory=dict, description="蓝图内容（描述、需求、约束、交付物提示等）"
    )


class BlueprintUpdateRequest(BaseModel):
    """更新蓝图请求"""
    title: Optional[str] = Field(None, max_length=200, description="蓝图标题")
    task_type: Optional[TaskType] = Field(None, description="任务类型")
    content: Optional[Dict[str, Any]] = Field(None, description="蓝图内容")


class BlueprintResponse(BaseModel):
    """蓝图响应"""
    id: uuid.UUID
    user_id: uuid.UUID
    title: str
    task_type: str
    content: Dict[str, Any]
    status: str
    version: int
    locked_at: Optional[datetime] = None
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class BlueprintListItem(BaseModel):
    """蓝图列表项"""
    id: uuid.UUID
    title: str
    task_type: str
    status: str
    version: int
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class BlueprintListResponse(BaseModel):
    """蓝图列表响应（分页）"""
    items: List[BlueprintListItem] = Field(description="蓝图列表")
    total: int = Field(description="总记录数")
    page: int = Field(description="当前页码")
    page_size: int = Field(description="每页条数")
    total_pages: int = Field(description="总页数")


# ============================================================
# 追问
# ============================================================

class QuestionItem(BaseModel):
    """追问项"""
    id: str = Field(description="追问ID")
    text: str = Field(description="追问内容")
    priority: QuestionPriority = Field(description="优先级")
    skipped: bool = Field(False, description="是否已跳过")
    skip_reason: Optional[str] = Field(None, description="跳过原因")


class QuestionsResponse(BaseModel):
    """追问列表响应"""
    blueprint_id: uuid.UUID
    questions: List[QuestionItem] = Field(description="追问列表")
    total: int = Field(description="总追问数")
    required_count: int = Field(description="必答追问数")
    skipped_count: int = Field(description="已跳过数")


class QuestionSkipRequest(BaseModel):
    """跳过追问请求"""
    reason: str = Field(
        ..., min_length=1, max_length=500, description="跳过原因"
    )


class SkipRateResponse(BaseModel):
    """跳过率响应"""
    blueprint_id: uuid.UUID
    total_questions: int = Field(description="总追问数")
    skipped_questions: int = Field(description="已跳过追问数")
    skip_rate: float = Field(description="跳过率 0-1")
    warning: bool = Field(description="是否需要警告（超过30%）")
