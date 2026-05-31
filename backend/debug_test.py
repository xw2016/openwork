"""调试脚本：检查注册端点"""
import asyncio
from httpx import ASGITransport, AsyncClient
from app.main import create_app

async def test():
    app = create_app()
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url='http://testserver') as client:
        # 测试健康检查
        r = await client.get('/health')
        print(f'Health: {r.status_code} {r.text[:200]}')
        
        # 测试注册
        r = await client.post('/v1/auth/register', json={
            'phone': '13800000001',
            'password': 'TestPass123',
            'nickname': 'test',
        })
        print(f'Register: {r.status_code} {r.text[:200]}')
        
        # 列出所有路由
        for route in app.routes:
            if hasattr(route, 'path'):
                methods = getattr(route, 'methods', set())
                print(f'  {route.path} {methods}')

asyncio.run(test())
