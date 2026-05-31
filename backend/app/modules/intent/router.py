"""
AI意图建模路由（桩）
"""

from fastapi import APIRouter

from app.schemas.common import ResponseBase

router = APIRouter(prefix="/v1/intent", tags=["AI意图建模"])


@router.post("/analyze", summary="意图分析（桩）")
async def analyze_intent():
    """分析用户输入的自然语言，提取任务意图"""
    return ResponseBase(code=501, message="功能尚未实现")


@router.post("/blueprint", summary="生成意图蓝图（桩）")
async def generate_blueprint():
    """根据意图分析结果生成结构化意图蓝图"""
    return ResponseBase(code=501, message="功能尚未实现")
