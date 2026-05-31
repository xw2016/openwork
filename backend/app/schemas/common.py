"""
通用响应模型
分页、错误响应等
"""

from __future__ import annotations

from typing import Any, Generic, List, Optional, TypeVar

from pydantic import BaseModel, Field

T = TypeVar("T")


class ResponseBase(BaseModel, Generic[T]):
    """统一响应格式"""
    code: int = Field(200, description="业务状态码")
    message: str = Field("success", description="提示信息")
    data: Optional[T] = Field(None, description="响应数据")


class PaginationParams(BaseModel):
    """分页请求参数"""
    page: int = Field(1, ge=1, description="页码")
    page_size: int = Field(20, ge=1, le=100, description="每页条数")

    @property
    def offset(self) -> int:
        return (self.page - 1) * self.page_size


class PaginatedData(BaseModel, Generic[T]):
    """分页响应数据"""
    items: List[T] = Field(description="数据列表")
    total: int = Field(description="总记录数")
    page: int = Field(description="当前页码")
    page_size: int = Field(description="每页条数")
    total_pages: int = Field(description="总页数")


class ErrorResponse(BaseModel):
    """错误响应"""
    code: int = Field(description="错误码")
    message: str = Field(description="错误信息")
    data: Any = Field(None, description="附加数据")
