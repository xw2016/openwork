"""
信用评分路由（桩）
"""

from fastapi import APIRouter

from app.schemas.common import ResponseBase

router = APIRouter(prefix="/v1/credit", tags=["信用评分"])


@router.get("/score/{user_id}", summary="查询信用分（桩）")
async def get_credit_score(user_id: str):
    return ResponseBase(code=501, message="功能尚未实现")


@router.get("/history/{user_id}", summary="信用历史（桩）")
async def get_credit_history(user_id: str):
    return ResponseBase(code=501, message="功能尚未实现")
