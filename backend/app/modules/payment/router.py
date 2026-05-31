"""
资金结算路由（桩）
"""

from fastapi import APIRouter

from app.schemas.common import ResponseBase

router = APIRouter(prefix="/v1/payment", tags=["资金结算"])


@router.post("/escrow", summary="托管资金（桩）")
async def escrow_funds():
    return ResponseBase(code=501, message="功能尚未实现")


@router.post("/release", summary="释放资金（桩）")
async def release_funds():
    return ResponseBase(code=501, message="功能尚未实现")


@router.post("/refund", summary="退款（桩）")
async def refund():
    return ResponseBase(code=501, message="功能尚未实现")


@router.get("/transactions", summary="交易记录（桩）")
async def list_transactions():
    return ResponseBase(code=501, message="功能尚未实现")
