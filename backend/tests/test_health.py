"""
基础健康检查测试
"""

import pytest
from httpx import ASGITransport, AsyncClient

from app.main import app


@pytest.mark.asyncio
async def test_health_endpoint():
    """测试 /health 端点返回 200"""
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.get("/health")

    assert response.status_code == 200
    data = response.json()
    assert data["code"] == 200
    assert data["message"] == "ok"
    assert data["data"]["project"] == "OpenWork"


@pytest.mark.asyncio
async def test_root_routes_exist():
    """测试各模块路由已注册（桩端点返回 501）"""
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        # 认证模块的注册接口返回 422（缺少 body），说明路由已注册
        resp = await client.post("/v1/auth/register")
        assert resp.status_code in (422, 405)

        # 桩端点应返回 501
        for path in [
            "/v1/intent/analyze",
            "/v1/contracts/",
            "/v1/market/tasks",
            "/v1/acceptance/evaluate",
            "/v1/payment/escrow",
            "/v1/credit/score/test",
            "/v1/blockchain/record",
        ]:
            resp = await client.get(path) if path.endswith("/") else await client.get(path)
            # 某些只有 POST，GET 会返回 405；POST 会返回 501 或 422
            assert resp.status_code in (200, 405, 422, 501)
