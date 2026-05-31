"""
AI验收路由（桩）
"""

from fastapi import APIRouter

from app.schemas.common import ResponseBase

router = APIRouter(prefix="/v1/acceptance", tags=["AI验收"])


@router.post("/evaluate", summary="AI验收评估（桩）")
async def evaluate_deliverable():
    return ResponseBase(code=501, message="功能尚未实现")


@router.get("/records", summary="验收记录列表（桩）")
async def list_records():
    return ResponseBase(code=501, message="功能尚未实现")


@router.get("/records/{record_id}", summary="验收记录详情（桩）")
async def get_record(record_id: str):
    return ResponseBase(code=501, message="功能尚未实现")
