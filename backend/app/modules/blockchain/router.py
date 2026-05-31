"""
链上存证路由（桩）
"""

from fastapi import APIRouter

from app.schemas.common import ResponseBase

router = APIRouter(prefix="/v1/blockchain", tags=["链上存证"])


@router.post("/record", summary="创建存证（桩）")
async def create_record():
    return ResponseBase(code=501, message="功能尚未实现")


@router.get("/records/{contract_id}", summary="查询存证（桩）")
async def list_records(contract_id: str):
    return ResponseBase(code=501, message="功能尚未实现")


@router.post("/verify", summary="验证存证（桩）")
async def verify_record():
    return ResponseBase(code=501, message="功能尚未实现")
