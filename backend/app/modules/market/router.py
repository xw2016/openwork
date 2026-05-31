"""
任务市场路由（桩）
"""

from fastapi import APIRouter

from app.schemas.common import ResponseBase

router = APIRouter(prefix="/v1/market", tags=["任务市场"])


@router.get("/tasks", summary="任务列表（桩）")
async def list_tasks():
    return ResponseBase(code=501, message="功能尚未实现")


@router.get("/tasks/{task_id}", summary="任务详情（桩）")
async def get_task(task_id: str):
    return ResponseBase(code=501, message="功能尚未实现")


@router.post("/tasks/{task_id}/bid", summary="竞标任务（桩）")
async def bid_task(task_id: str):
    return ResponseBase(code=501, message="功能尚未实现")
