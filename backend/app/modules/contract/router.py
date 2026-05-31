"""
任务合约路由（桩）
"""

from fastapi import APIRouter

from app.schemas.common import ResponseBase

router = APIRouter(prefix="/v1/contracts", tags=["任务合约"])


@router.post("/", summary="创建合约（桩）")
async def create_contract():
    return ResponseBase(code=501, message="功能尚未实现")


@router.get("/", summary="合约列表（桩）")
async def list_contracts():
    return ResponseBase(code=501, message="功能尚未实现")


@router.get("/{contract_id}", summary="合约详情（桩）")
async def get_contract(contract_id: str):
    return ResponseBase(code=501, message="功能尚未实现")


@router.put("/{contract_id}", summary="更新合约（桩）")
async def update_contract(contract_id: str):
    return ResponseBase(code=501, message="功能尚未实现")


@router.post("/{contract_id}/confirm", summary="确认合约（桩）")
async def confirm_contract(contract_id: str):
    return ResponseBase(code=501, message="功能尚未实现")
