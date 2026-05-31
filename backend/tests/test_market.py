"""
任务市场模块完整单元测试
覆盖：
- 市场任务列表（分页、筛选、排序、关键词搜索、金额过滤）
- 市场任务详情
- 接单（状态校验、自接单校验）
- 提交交付物（状态校验、权限校验）
"""

from __future__ import annotations

import uuid
from decimal import Decimal

import pytest
import pytest_asyncio
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.security import create_access_token, hash_password
from app.models.contract import Contract, ContractStatus, TaskType
from app.models.deliverable import AcceptanceStatus, Deliverable
from app.models.user import User, UserStatus, UserType
from app.modules.market import service as market_service
from app.modules.market import deliverable_ops


# ============================================================
# 辅助函数
# ============================================================


async def _create_user(
    db: AsyncSession,
    user_type: UserType = UserType.FREELANCER,
    phone: str = "13900000001",
    email: str = None,
    nickname: str = "测试用户",
    credit_score: int = 600,
) -> User:
    """创建测试用户"""
    user = User(
        phone=phone,
        email=email,
        nickname=nickname,
        user_type=user_type,
        hashed_password=hash_password("TestPass123"),
        status=UserStatus.ACTIVE,
        credit_score=credit_score,
    )
    db.add(user)
    await db.commit()
    await db.refresh(user)
    return user


def _get_auth_headers(user: User) -> dict:
    """获取认证 headers"""
    token = create_access_token(
        data={"sub": str(user.id), "type": "access", "role": user.user_type.value}
    )
    return {"Authorization": f"Bearer {token}"}


async def _create_contract_in_db(
    db: AsyncSession,
    employer_id: uuid.UUID,
    status: ContractStatus = ContractStatus.PENDING,
    title: str = "市场测试任务",
    base_amount: Decimal = Decimal("5000.00"),
    task_type: TaskType = TaskType.DEVELOPMENT,
) -> Contract:
    """直接在数据库中创建合约"""
    contract = Contract(
        contract_no=f"OW-MKT-{uuid.uuid4().hex[:8]}",
        employer_id=employer_id,
        title=title,
        task_type=task_type,
        intent_blueprint={},
        deliverables=[],
        base_amount=base_amount,
        bonus_amount=Decimal("0.00"),
        commission_rate=Decimal("0.05"),
        status=status,
    )
    db.add(contract)
    await db.commit()
    await db.refresh(contract)
    return contract


async def _create_deliverable_in_db(
    db: AsyncSession,
    contract_id: uuid.UUID,
    name: str = "源代码",
    deliverable_index: int = 1,
) -> Deliverable:
    """直接在数据库中创建交付物"""
    deliverable = Deliverable(
        contract_id=contract_id,
        deliverable_index=deliverable_index,
        name=name,
        required_format="Git 仓库",
        acceptance_criteria={"description": "符合编码规范"},
        acceptance_status=AcceptanceStatus.NOT_SUBMITTED,
    )
    db.add(deliverable)
    await db.commit()
    await db.refresh(deliverable)
    return deliverable


# ============================================================
# 市场任务列表测试
# ============================================================


class TestListMarketTasks:
    """市场任务列表查询测试"""

    @pytest.mark.asyncio
    async def test_list_tasks_empty(
        self, client: AsyncClient, db_session: AsyncSession
    ):
        """测试空列表"""
        freelancer = await _create_user(
            db_session, UserType.FREELANCER, phone="13900000010"
        )
        headers = _get_auth_headers(freelancer)

        resp = await client.get("/v1/market/tasks", headers=headers)
        assert resp.status_code == 200
        data = resp.json()["data"]
        assert data["total"] == 0
        assert data["items"] == []

    @pytest.mark.asyncio
    async def test_list_tasks_only_pending(
        self, client: AsyncClient, db_session: AsyncSession
    ):
        """测试只展示 pending 状态的合约"""
        employer = await _create_user(
            db_session, UserType.EMPLOYER, phone="13900000011", nickname="雇主"
        )
        freelancer = await _create_user(
            db_session, UserType.FREELANCER, phone="13900000012", nickname="接单者"
        )
        headers = _get_auth_headers(freelancer)

        # 创建 pending 合约（应该出现）
        await _create_contract_in_db(
            db_session, employer.id, ContractStatus.PENDING, "待接单任务"
        )
        # 创建 draft 合约（不应出现）
        await _create_contract_in_db(
            db_session, employer.id, ContractStatus.DRAFT, "草稿任务"
        )
        # 创建 in_progress 合约（不应出现）
        await _create_contract_in_db(
            db_session, employer.id, ContractStatus.IN_PROGRESS, "进行中任务"
        )

        resp = await client.get("/v1/market/tasks", headers=headers)
        assert resp.status_code == 200
        data = resp.json()["data"]
        assert data["total"] == 1
        assert data["items"][0]["title"] == "待接单任务"

    @pytest.mark.asyncio
    async def test_list_tasks_with_employer_info(
        self, client: AsyncClient, db_session: AsyncSession
    ):
        """测试任务列表包含雇主昵称和信用分"""
        employer = await _create_user(
            db_session,
            UserType.EMPLOYER,
            phone="13900000013",
            nickname="优质雇主",
            credit_score=750,
        )
        freelancer = await _create_user(
            db_session, UserType.FREELANCER, phone="13900000014"
        )
        headers = _get_auth_headers(freelancer)

        await _create_contract_in_db(db_session, employer.id)

        resp = await client.get("/v1/market/tasks", headers=headers)
        assert resp.status_code == 200
        items = resp.json()["data"]["items"]
        assert len(items) == 1
        assert items[0]["employer_nickname"] == "优质雇主"
        assert items[0]["employer_credit_score"] == 750

    @pytest.mark.asyncio
    async def test_list_tasks_keyword_search(
        self, client: AsyncClient, db_session: AsyncSession
    ):
        """测试关键词搜索标题"""
        employer = await _create_user(
            db_session, UserType.EMPLOYER, phone="13900000015"
        )
        freelancer = await _create_user(
            db_session, UserType.FREELANCER, phone="13900000016"
        )
        headers = _get_auth_headers(freelancer)

        await _create_contract_in_db(
            db_session, employer.id, title="Python开发任务"
        )
        await _create_contract_in_db(
            db_session, employer.id, title="UI设计任务"
        )
        await _create_contract_in_db(
            db_session, employer.id, title="Python爬虫任务"
        )

        # 搜索 Python
        resp = await client.get(
            "/v1/market/tasks", params={"keyword": "Python"}, headers=headers
        )
        assert resp.status_code == 200
        data = resp.json()["data"]
        assert data["total"] == 2

        # 搜索 设计
        resp = await client.get(
            "/v1/market/tasks", params={"keyword": "设计"}, headers=headers
        )
        assert resp.status_code == 200
        data = resp.json()["data"]
        assert data["total"] == 1
        assert "设计" in data["items"][0]["title"]

    @pytest.mark.asyncio
    async def test_list_tasks_amount_filter(
        self, client: AsyncClient, db_session: AsyncSession
    ):
        """测试金额范围筛选"""
        employer = await _create_user(
            db_session, UserType.EMPLOYER, phone="13900000017"
        )
        freelancer = await _create_user(
            db_session, UserType.FREELANCER, phone="13900000018"
        )
        headers = _get_auth_headers(freelancer)

        await _create_contract_in_db(
            db_session, employer.id, title="小任务", base_amount=Decimal("1000.00")
        )
        await _create_contract_in_db(
            db_session, employer.id, title="中任务", base_amount=Decimal("5000.00")
        )
        await _create_contract_in_db(
            db_session, employer.id, title="大任务", base_amount=Decimal("10000.00")
        )

        # min_amount = 3000
        resp = await client.get(
            "/v1/market/tasks", params={"min_amount": 3000}, headers=headers
        )
        assert resp.status_code == 200
        data = resp.json()["data"]
        assert data["total"] == 2

        # max_amount = 5000
        resp = await client.get(
            "/v1/market/tasks", params={"max_amount": 5000}, headers=headers
        )
        assert resp.status_code == 200
        data = resp.json()["data"]
        assert data["total"] == 2

        # min + max
        resp = await client.get(
            "/v1/market/tasks",
            params={"min_amount": 4000, "max_amount": 8000},
            headers=headers,
        )
        assert resp.status_code == 200
        data = resp.json()["data"]
        assert data["total"] == 1

    @pytest.mark.asyncio
    async def test_list_tasks_sort(
        self, client: AsyncClient, db_session: AsyncSession
    ):
        """测试排序"""
        employer = await _create_user(
            db_session, UserType.EMPLOYER, phone="13900000019"
        )
        freelancer = await _create_user(
            db_session, UserType.FREELANCER, phone="13900000020"
        )
        headers = _get_auth_headers(freelancer)

        await _create_contract_in_db(
            db_session, employer.id, title="低价任务", base_amount=Decimal("1000.00")
        )
        await _create_contract_in_db(
            db_session, employer.id, title="高价任务", base_amount=Decimal("10000.00")
        )

        # amount_asc
        resp = await client.get(
            "/v1/market/tasks", params={"sort": "amount_asc"}, headers=headers
        )
        items = resp.json()["data"]["items"]
        assert items[0]["title"] == "低价任务"
        assert items[1]["title"] == "高价任务"

        # amount_desc
        resp = await client.get(
            "/v1/market/tasks", params={"sort": "amount_desc"}, headers=headers
        )
        items = resp.json()["data"]["items"]
        assert items[0]["title"] == "高价任务"
        assert items[1]["title"] == "低价任务"

    @pytest.mark.asyncio
    async def test_list_tasks_pagination(
        self, client: AsyncClient, db_session: AsyncSession
    ):
        """测试分页"""
        employer = await _create_user(
            db_session, UserType.EMPLOYER, phone="13900000021"
        )
        freelancer = await _create_user(
            db_session, UserType.FREELANCER, phone="13900000022"
        )
        headers = _get_auth_headers(freelancer)

        # 创建5个合约
        for i in range(5):
            await _create_contract_in_db(
                db_session, employer.id, title=f"任务 {i+1}"
            )

        # 第1页，每页2条
        resp = await client.get(
            "/v1/market/tasks", params={"page": 1, "size": 2}, headers=headers
        )
        data = resp.json()["data"]
        assert data["total"] == 5
        assert len(data["items"]) == 2
        assert data["total_pages"] == 3

        # 第3页，每页2条（最后1条）
        resp = await client.get(
            "/v1/market/tasks", params={"page": 3, "size": 2}, headers=headers
        )
        data = resp.json()["data"]
        assert len(data["items"]) == 1

    @pytest.mark.asyncio
    async def test_list_tasks_task_type_filter(
        self, client: AsyncClient, db_session: AsyncSession
    ):
        """测试任务类型过滤"""
        employer = await _create_user(
            db_session, UserType.EMPLOYER, phone="13900000023"
        )
        freelancer = await _create_user(
            db_session, UserType.FREELANCER, phone="13900000024"
        )
        headers = _get_auth_headers(freelancer)

        await _create_contract_in_db(
            db_session, employer.id, title="开发任务", task_type=TaskType.DEVELOPMENT
        )
        await _create_contract_in_db(
            db_session, employer.id, title="设计任务", task_type=TaskType.DESIGN
        )

        resp = await client.get(
            "/v1/market/tasks", params={"task_type": "design"}, headers=headers
        )
        data = resp.json()["data"]
        assert data["total"] == 1
        assert data["items"][0]["task_type"] == "design"


# ============================================================
# 市场任务详情测试
# ============================================================


class TestGetMarketTask:
    """市场任务详情测试"""

    @pytest.mark.asyncio
    async def test_get_task_success(
        self, client: AsyncClient, db_session: AsyncSession
    ):
        """测试获取任务详情成功"""
        employer = await _create_user(
            db_session,
            UserType.EMPLOYER,
            phone="13900000030",
            nickname="详情雇主",
            credit_score=800,
        )
        freelancer = await _create_user(
            db_session, UserType.FREELANCER, phone="13900000031"
        )
        headers = _get_auth_headers(freelancer)

        contract = await _create_contract_in_db(db_session, employer.id)

        resp = await client.get(
            f"/v1/market/tasks/{contract.id}", headers=headers
        )
        assert resp.status_code == 200
        data = resp.json()["data"]
        assert data["title"] == "市场测试任务"
        assert data["employer_nickname"] == "详情雇主"
        assert data["employer_credit_score"] == 800
        assert data["status"] == "pending"

    @pytest.mark.asyncio
    async def test_get_task_not_found(
        self, client: AsyncClient, db_session: AsyncSession
    ):
        """测试任务不存在"""
        freelancer = await _create_user(
            db_session, UserType.FREELANCER, phone="13900000032"
        )
        headers = _get_auth_headers(freelancer)

        fake_id = str(uuid.uuid4())
        resp = await client.get(f"/v1/market/tasks/{fake_id}", headers=headers)
        assert resp.status_code == 404


# ============================================================
# 接单测试
# ============================================================


class TestBidTask:
    """接单测试"""

    @pytest.mark.asyncio
    async def test_bid_success(
        self, client: AsyncClient, db_session: AsyncSession
    ):
        """测试接单成功"""
        employer = await _create_user(
            db_session, UserType.EMPLOYER, phone="13900000040"
        )
        freelancer = await _create_user(
            db_session, UserType.FREELANCER, phone="13900000041"
        )
        headers = _get_auth_headers(freelancer)

        contract = await _create_contract_in_db(
            db_session, employer.id, ContractStatus.PENDING
        )

        resp = await client.post(
            f"/v1/market/tasks/{contract.id}/bid", headers=headers
        )
        assert resp.status_code == 200
        body = resp.json()
        assert body["message"] == "接单成功"
        assert body["data"]["status"] == "in_progress"
        assert body["data"]["freelancer_id"] == str(freelancer.id)

    @pytest.mark.asyncio
    async def test_bid_own_task_fails_via_service(
        self, db_session: AsyncSession
    ):
        """测试不能接自己的单（通过 service 层直接调用，API 层雇主会被权限中间件拦截）"""
        employer = await _create_user(
            db_session, UserType.EMPLOYER, phone="13900000042"
        )
        contract = await _create_contract_in_db(
            db_session, employer.id, ContractStatus.PENDING
        )

        with pytest.raises(ValueError, match="自己"):
            await market_service.bid_task(
                db_session, contract.id, employer.id
            )

    @pytest.mark.asyncio
    async def test_bid_non_pending_fails(
        self, client: AsyncClient, db_session: AsyncSession
    ):
        """测试接单非 pending 状态的合约失败"""
        employer = await _create_user(
            db_session, UserType.EMPLOYER, phone="13900000043"
        )
        freelancer = await _create_user(
            db_session, UserType.FREELANCER, phone="13900000044"
        )
        headers = _get_auth_headers(freelancer)

        # draft 状态的合约
        contract = await _create_contract_in_db(
            db_session, employer.id, ContractStatus.DRAFT
        )

        resp = await client.post(
            f"/v1/market/tasks/{contract.id}/bid", headers=headers
        )
        body = resp.json()
        assert resp.status_code == 400
        assert "无法接单" in body.get("message", body.get("detail", ""))

    @pytest.mark.asyncio
    async def test_bid_not_found(
        self, client: AsyncClient, db_session: AsyncSession
    ):
        """测试接单不存在的任务"""
        freelancer = await _create_user(
            db_session, UserType.FREELANCER, phone="13900000045"
        )
        headers = _get_auth_headers(freelancer)

        fake_id = str(uuid.uuid4())
        resp = await client.post(
            f"/v1/market/tasks/{fake_id}/bid", headers=headers
        )
        assert resp.status_code == 400
        assert "不存在" in resp.json().get("message", resp.json().get("detail", ""))

    @pytest.mark.asyncio
    async def test_bid_by_employer_forbidden(
        self, client: AsyncClient, db_session: AsyncSession
    ):
        """测试雇主角色不能接单"""
        employer = await _create_user(
            db_session, UserType.EMPLOYER, phone="13900000046", nickname="雇主A"
        )
        other_employer = await _create_user(
            db_session, UserType.EMPLOYER, phone="13900000047", nickname="雇主B"
        )
        headers = _get_auth_headers(other_employer)

        contract = await _create_contract_in_db(
            db_session, employer.id, ContractStatus.PENDING
        )

        resp = await client.post(
            f"/v1/market/tasks/{contract.id}/bid", headers=headers
        )
        assert resp.status_code == 403


# ============================================================
# 提交交付物测试
# ============================================================


class TestSubmitDeliverable:
    """提交交付物测试"""

    @pytest.mark.asyncio
    async def test_submit_deliverable_success(
        self, client: AsyncClient, db_session: AsyncSession
    ):
        """测试提交交付物成功"""
        employer = await _create_user(
            db_session, UserType.EMPLOYER, phone="13900000050"
        )
        freelancer = await _create_user(
            db_session, UserType.FREELANCER, phone="13900000051"
        )
        headers = _get_auth_headers(freelancer)

        contract = await _create_contract_in_db(
            db_session, employer.id, ContractStatus.IN_PROGRESS
        )
        # 手动设置 freelancer_id
        contract.freelancer_id = freelancer.id
        await db_session.commit()
        await db_session.refresh(contract)

        deliverable = await _create_deliverable_in_db(db_session, contract.id)

        resp = await client.post(
            f"/v1/market/tasks/{contract.id}/deliverables/{deliverable.id}/submit",
            json={
                "file_url": "https://example.com/code.zip",
                "file_hash": "abc123def456",
            },
            headers=headers,
        )
        assert resp.status_code == 200
        data = resp.json()["data"]
        assert data["file_url"] == "https://example.com/code.zip"
        assert data["file_hash"] == "abc123def456"
        assert data["submit_version"] == 2  # 默认是1，提交后+1
        assert data["acceptance_status"] == "pending"
        assert data["submit_time"] is not None

    @pytest.mark.asyncio
    async def test_submit_deliverable_not_in_progress(
        self, client: AsyncClient, db_session: AsyncSession
    ):
        """测试合约非 in_progress 状态时提交失败"""
        employer = await _create_user(
            db_session, UserType.EMPLOYER, phone="13900000052"
        )
        freelancer = await _create_user(
            db_session, UserType.FREELANCER, phone="13900000053"
        )
        headers = _get_auth_headers(freelancer)

        contract = await _create_contract_in_db(
            db_session, employer.id, ContractStatus.PENDING
        )
        deliverable = await _create_deliverable_in_db(db_session, contract.id)

        resp = await client.post(
            f"/v1/market/tasks/{contract.id}/deliverables/{deliverable.id}/submit",
            json={"file_url": "https://example.com/code.zip"},
            headers=headers,
        )
        body = resp.json()
        assert resp.status_code == 400
        assert "无法提交交付物" in body.get("message", body.get("detail", ""))

    @pytest.mark.asyncio
    async def test_submit_deliverable_wrong_freelancer(
        self, client: AsyncClient, db_session: AsyncSession
    ):
        """测试非合约承接者提交失败"""
        employer = await _create_user(
            db_session, UserType.EMPLOYER, phone="13900000054"
        )
        freelancer = await _create_user(
            db_session, UserType.FREELANCER, phone="13900000055"
        )
        other_freelancer = await _create_user(
            db_session, UserType.FREELANCER, phone="13900000056", nickname="其他接单者"
        )
        headers = _get_auth_headers(other_freelancer)

        contract = await _create_contract_in_db(
            db_session, employer.id, ContractStatus.IN_PROGRESS
        )
        contract.freelancer_id = freelancer.id
        await db_session.commit()
        await db_session.refresh(contract)

        deliverable = await _create_deliverable_in_db(db_session, contract.id)

        resp = await client.post(
            f"/v1/market/tasks/{contract.id}/deliverables/{deliverable.id}/submit",
            json={"file_url": "https://example.com/code.zip"},
            headers=headers,
        )
        body = resp.json()
        assert resp.status_code == 400
        assert "承接者" in body.get("message", body.get("detail", ""))

    @pytest.mark.asyncio
    async def test_submit_deliverable_not_found(
        self, client: AsyncClient, db_session: AsyncSession
    ):
        """测试提交不存在的交付物"""
        employer = await _create_user(
            db_session, UserType.EMPLOYER, phone="13900000057"
        )
        freelancer = await _create_user(
            db_session, UserType.FREELANCER, phone="13900000058"
        )
        headers = _get_auth_headers(freelancer)

        contract = await _create_contract_in_db(
            db_session, employer.id, ContractStatus.IN_PROGRESS
        )
        contract.freelancer_id = freelancer.id
        await db_session.commit()

        fake_deliverable_id = str(uuid.uuid4())
        resp = await client.post(
            f"/v1/market/tasks/{contract.id}/deliverables/{fake_deliverable_id}/submit",
            json={"file_url": "https://example.com/code.zip"},
            headers=headers,
        )
        body = resp.json()
        assert resp.status_code == 400
        assert "不存在" in body.get("message", body.get("detail", ""))


# ============================================================
# Service 层直接测试
# ============================================================


class TestMarketService:
    """市场服务层单元测试"""

    @pytest.mark.asyncio
    async def test_list_market_tasks_service(self, db_session: AsyncSession):
        """测试 list_market_tasks 服务函数"""
        employer = await _create_user(
            db_session, UserType.EMPLOYER, phone="13900000060"
        )
        await _create_contract_in_db(db_session, employer.id)

        items, total = await market_service.list_market_tasks(db_session)
        assert total == 1
        assert len(items) == 1
        assert items[0]["employer_nickname"] == "测试用户"

    @pytest.mark.asyncio
    async def test_bid_task_service_success(self, db_session: AsyncSession):
        """测试 bid_task 服务函数成功"""
        employer = await _create_user(
            db_session, UserType.EMPLOYER, phone="13900000061"
        )
        freelancer = await _create_user(
            db_session, UserType.FREELANCER, phone="13900000062"
        )
        contract = await _create_contract_in_db(
            db_session, employer.id, ContractStatus.PENDING
        )

        result = await market_service.bid_task(
            db_session, contract.id, freelancer.id
        )
        assert result.status == ContractStatus.IN_PROGRESS
        assert result.freelancer_id == freelancer.id

    @pytest.mark.asyncio
    async def test_bid_task_service_self_bid(self, db_session: AsyncSession):
        """测试 bid_task 接自己的单"""
        employer = await _create_user(
            db_session, UserType.EMPLOYER, phone="13900000063"
        )
        contract = await _create_contract_in_db(
            db_session, employer.id, ContractStatus.PENDING
        )

        with pytest.raises(ValueError, match="自己"):
            await market_service.bid_task(
                db_session, contract.id, employer.id
            )

    @pytest.mark.asyncio
    async def test_submit_deliverable_service(self, db_session: AsyncSession):
        """测试 submit_deliverable 服务函数"""
        employer = await _create_user(
            db_session, UserType.EMPLOYER, phone="13900000064"
        )
        freelancer = await _create_user(
            db_session, UserType.FREELANCER, phone="13900000065"
        )
        contract = await _create_contract_in_db(
            db_session, employer.id, ContractStatus.IN_PROGRESS
        )
        contract.freelancer_id = freelancer.id
        await db_session.commit()

        deliverable = await _create_deliverable_in_db(db_session, contract.id)

        result = await deliverable_ops.submit_deliverable(
            db_session,
            contract_id=contract.id,
            deliverable_id=deliverable.id,
            freelancer_id=freelancer.id,
            file_url="https://example.com/result.tar.gz",
            file_hash="sha256hash",
        )
        assert result.file_url == "https://example.com/result.tar.gz"
        assert result.file_hash == "sha256hash"
        assert result.submit_version == 2
        assert result.acceptance_status == AcceptanceStatus.PENDING
        assert result.submit_time is not None
