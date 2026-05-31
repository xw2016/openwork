"""
合约模块完整单元测试
覆盖：
- 合约创建（草稿）
- 合约列表查询（分页、角色筛选、状态筛选）
- 合约详情查看
- 合约更新（仅 draft）
- 合约状态流转（发布、接单、提交验收、完成、终止）
- 状态机非法转换验证
- 交付物清单自动生成与查询
- 结算配置校验
- 权限校验
"""

from __future__ import annotations

import uuid
from decimal import Decimal
from unittest.mock import AsyncMock

import pytest
import pytest_asyncio
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.security import hash_password
from app.models.contract import Contract, ContractStatus, TaskType
from app.models.deliverable import Deliverable
from app.models.user import User, UserStatus, UserType
from app.modules.contract import service as contract_service
from app.modules.contract import deliverable_service
from app.modules.contract.router import (
    calculate_commission,
    calculate_total_payable,
    validate_settlement_config,
)


# ============================================================
# 辅助函数
# ============================================================


async def _create_user(
    db: AsyncSession,
    user_type: UserType = UserType.EMPLOYER,
    phone: str = "13800000001",
    email: str = None,
    nickname: str = "测试用户",
) -> User:
    """创建测试用户"""
    user = User(
        phone=phone,
        email=email,
        nickname=nickname,
        user_type=user_type,
        hashed_password=hash_password("TestPass123"),
        status=UserStatus.ACTIVE,
    )
    db.add(user)
    await db.commit()
    await db.refresh(user)
    return user


def _get_auth_headers(user: User, client: AsyncClient = None) -> dict:
    """获取认证 headers（直接构造 JWT）"""
    from app.core.security import create_access_token

    token = create_access_token(
        data={"sub": str(user.id), "type": "access", "role": user.user_type.value}
    )
    return {"Authorization": f"Bearer {token}"}


def _sample_contract_data() -> dict:
    """样本合约创建数据"""
    return {
        "title": "测试任务",
        "task_type": "development",
        "intent_blueprint": {"requirements": "实现用户管理模块"},
        "deliverables": [],
        "base_amount": "10000.00",
        "bonus_amount": "2000.00",
        "bonus_condition": {"condition": "提前3天完成"},
        "deadline": "2026-12-31T23:59:59Z",
    }


async def _create_contract_via_api(
    client: AsyncClient, headers: dict, data: dict = None
) -> dict:
    """通过 API 创建合约并返回响应数据"""
    if data is None:
        data = _sample_contract_data()
    resp = await client.post("/v1/contracts/", json=data, headers=headers)
    assert resp.status_code == 201, f"创建合约失败: {resp.text}"
    return resp.json()["data"]


async def _create_contract_in_db(
    db: AsyncSession,
    employer_id: uuid.UUID,
    status: ContractStatus = ContractStatus.DRAFT,
    freelancer_id: uuid.UUID = None,
) -> Contract:
    """直接在数据库中创建合约（绕过 API，用于快速准备测试数据）"""
    contract = Contract(
        contract_no=f"OW-TEST-{uuid.uuid4().hex[:8]}",
        employer_id=employer_id,
        freelancer_id=freelancer_id,
        title="DB直接创建的测试合约",
        task_type=TaskType.DEVELOPMENT,
        intent_blueprint={},
        deliverables=[],
        base_amount=Decimal("5000.00"),
        bonus_amount=Decimal("0.00"),
        commission_rate=Decimal("0.05"),
        status=status,
    )
    db.add(contract)
    await db.commit()
    await db.refresh(contract)
    return contract


# ============================================================
# 合约创建测试
# ============================================================


class TestCreateContract:
    """合约创建测试"""

    @pytest.mark.asyncio
    async def test_create_contract_success(
        self, client: AsyncClient, db_session: AsyncSession
    ):
        """测试雇主成功创建合约草稿"""
        employer = await _create_user(
            db_session, UserType.EMPLOYER, phone="13800000001"
        )
        headers = _get_auth_headers(employer)
        data = _sample_contract_data()

        resp = await client.post("/v1/contracts/", json=data, headers=headers)
        assert resp.status_code == 201
        body = resp.json()
        assert body["code"] == 201
        assert body["message"] == "合约创建成功"
        assert body["data"]["title"] == "测试任务"
        assert body["data"]["task_type"] == "development"
        assert body["data"]["status"] == "draft"
        assert body["data"]["contract_no"].startswith("OW-")
        assert body["data"]["base_amount"] == "10000.00"
        assert body["data"]["employer_id"] == str(employer.id)

    @pytest.mark.asyncio
    async def test_create_contract_invalid_amount(
        self, client: AsyncClient, db_session: AsyncSession
    ):
        """测试创建合约时基础金额为0"""
        employer = await _create_user(
            db_session, UserType.EMPLOYER, phone="13800000002"
        )
        headers = _get_auth_headers(employer)
        data = _sample_contract_data()
        data["base_amount"] = "0"

        resp = await client.post("/v1/contracts/", json=data, headers=headers)
        # 全局异常处理器将 HTTPException 包装为 {code, message, data} 格式
        body = resp.json()
        assert resp.status_code == 400
        assert "基础金额必须大于0" in body.get("message", body.get("detail", ""))

    @pytest.mark.asyncio
    async def test_create_contract_negative_amount(
        self, client: AsyncClient, db_session: AsyncSession
    ):
        """测试创建合约时基础金额为负数"""
        employer = await _create_user(
            db_session, UserType.EMPLOYER, phone="13800000003"
        )
        headers = _get_auth_headers(employer)
        data = _sample_contract_data()
        data["base_amount"] = "-100"

        # Pydantic 验证（ge=0）会返回 422
        resp = await client.post("/v1/contracts/", json=data, headers=headers)
        assert resp.status_code == 422


# ============================================================
# 合约查询测试
# ============================================================


class TestGetContract:
    """合约详情查询测试"""

    @pytest.mark.asyncio
    async def test_get_contract_success(
        self, client: AsyncClient, db_session: AsyncSession
    ):
        """测试雇主查看自己的合约"""
        employer = await _create_user(
            db_session, UserType.EMPLOYER, phone="13800000010"
        )
        headers = _get_auth_headers(employer)
        created = await _create_contract_via_api(client, headers)

        resp = await client.get(
            f"/v1/contracts/{created['id']}", headers=headers
        )
        assert resp.status_code == 200
        assert resp.json()["data"]["id"] == created["id"]

    @pytest.mark.asyncio
    async def test_get_contract_not_found(
        self, client: AsyncClient, db_session: AsyncSession
    ):
        """测试查询不存在的合约"""
        employer = await _create_user(
            db_session, UserType.EMPLOYER, phone="13800000011"
        )
        headers = _get_auth_headers(employer)
        fake_id = str(uuid.uuid4())

        resp = await client.get(f"/v1/contracts/{fake_id}", headers=headers)
        assert resp.status_code == 404

    @pytest.mark.asyncio
    async def test_get_contract_unauthorized_user(
        self, client: AsyncClient, db_session: AsyncSession
    ):
        """测试无权用户查看他人合约"""
        employer = await _create_user(
            db_session, UserType.EMPLOYER, phone="13800000012"
        )
        other = await _create_user(
            db_session, UserType.FREELANCER, phone="13800000013", nickname="其他用户"
        )
        headers_employer = _get_auth_headers(employer)
        headers_other = _get_auth_headers(other)
        created = await _create_contract_via_api(client, headers_employer)

        resp = await client.get(
            f"/v1/contracts/{created['id']}", headers=headers_other
        )
        assert resp.status_code == 403


# ============================================================
# 合约列表测试
# ============================================================


class TestListContracts:
    """合约列表查询测试"""

    @pytest.mark.asyncio
    async def test_list_contracts_empty(
        self, client: AsyncClient, db_session: AsyncSession
    ):
        """测试空列表"""
        employer = await _create_user(
            db_session, UserType.EMPLOYER, phone="13800000020"
        )
        headers = _get_auth_headers(employer)

        resp = await client.get("/v1/contracts/", headers=headers)
        assert resp.status_code == 200
        data = resp.json()["data"]
        assert data["total"] == 0
        assert data["items"] == []

    @pytest.mark.asyncio
    async def test_list_contracts_with_data(
        self, client: AsyncClient, db_session: AsyncSession
    ):
        """测试有数据的列表"""
        employer = await _create_user(
            db_session, UserType.EMPLOYER, phone="13800000021"
        )
        headers = _get_auth_headers(employer)

        # 创建3个合约
        for i in range(3):
            data = _sample_contract_data()
            data["title"] = f"任务 {i+1}"
            await client.post("/v1/contracts/", json=data, headers=headers)

        resp = await client.get("/v1/contracts/", headers=headers)
        assert resp.status_code == 200
        result = resp.json()["data"]
        assert result["total"] == 3
        assert len(result["items"]) == 3

    @pytest.mark.asyncio
    async def test_list_contracts_filter_by_status(
        self, client: AsyncClient, db_session: AsyncSession
    ):
        """测试按状态筛选"""
        employer = await _create_user(
            db_session, UserType.EMPLOYER, phone="13800000022"
        )
        headers = _get_auth_headers(employer)

        created = await _create_contract_via_api(client, headers)

        # 只查 draft 状态
        resp = await client.get(
            "/v1/contracts/", params={"status": "draft"}, headers=headers
        )
        assert resp.status_code == 200
        assert resp.json()["data"]["total"] == 1

        # 只查 pending 状态（应该为空）
        resp = await client.get(
            "/v1/contracts/", params={"status": "pending"}, headers=headers
        )
        assert resp.status_code == 200
        assert resp.json()["data"]["total"] == 0


# ============================================================
# 合约更新测试
# ============================================================


class TestUpdateContract:
    """合约更新测试"""

    @pytest.mark.asyncio
    async def test_update_contract_success(
        self, client: AsyncClient, db_session: AsyncSession
    ):
        """测试更新草稿合约"""
        employer = await _create_user(
            db_session, UserType.EMPLOYER, phone="13800000030"
        )
        headers = _get_auth_headers(employer)
        created = await _create_contract_via_api(client, headers)

        resp = await client.put(
            f"/v1/contracts/{created['id']}",
            json={"title": "更新后的标题"},
            headers=headers,
        )
        assert resp.status_code == 200
        assert resp.json()["data"]["title"] == "更新后的标题"

    @pytest.mark.asyncio
    async def test_update_non_draft_contract_fails(
        self, client: AsyncClient, db_session: AsyncSession
    ):
        """测试更新非草稿状态合约失败"""
        employer = await _create_user(
            db_session, UserType.EMPLOYER, phone="13800000031"
        )
        headers = _get_auth_headers(employer)
        created = await _create_contract_via_api(client, headers)

        # 先发布
        await client.post(
            f"/v1/contracts/{created['id']}/publish", headers=headers
        )

        # 再尝试更新
        resp = await client.put(
            f"/v1/contracts/{created['id']}",
            json={"title": "不应成功"},
            headers=headers,
        )
        body = resp.json()
        assert resp.status_code == 400
        assert "草稿状态" in body.get("message", body.get("detail", ""))


# ============================================================
# 合约状态流转测试
# ============================================================


class TestContractStatusTransitions:
    """合约状态流转测试"""

    @pytest.mark.asyncio
    async def test_full_lifecycle(
        self, client: AsyncClient, db_session: AsyncSession
    ):
        """测试完整的合约生命周期：draft -> pending -> in_progress -> review -> completed"""
        employer = await _create_user(
            db_session, UserType.EMPLOYER, phone="13800000040"
        )
        freelancer = await _create_user(
            db_session,
            UserType.FREELANCER,
            phone="13800000041",
            nickname="自由职业者",
        )
        employer_headers = _get_auth_headers(employer)
        freelancer_headers = _get_auth_headers(freelancer)

        # 1. 创建
        created = await _create_contract_via_api(client, employer_headers)
        assert created["status"] == "draft"

        # 2. 发布
        resp = await client.post(
            f"/v1/contracts/{created['id']}/publish", headers=employer_headers
        )
        assert resp.status_code == 200
        assert resp.json()["data"]["status"] == "pending"

        # 3. 接单
        resp = await client.post(
            f"/v1/contracts/{created['id']}/accept", headers=freelancer_headers
        )
        assert resp.status_code == 200
        assert resp.json()["data"]["status"] == "in_progress"
        assert resp.json()["data"]["freelancer_id"] == str(freelancer.id)

        # 4. 提交验收
        resp = await client.post(
            f"/v1/contracts/{created['id']}/submit", headers=freelancer_headers
        )
        assert resp.status_code == 200
        assert resp.json()["data"]["status"] == "review"

        # 5. 完成
        resp = await client.post(
            f"/v1/contracts/{created['id']}/complete", headers=employer_headers
        )
        assert resp.status_code == 200
        assert resp.json()["data"]["status"] == "completed"

    @pytest.mark.asyncio
    async def test_publish_non_draft_fails(
        self, client: AsyncClient, db_session: AsyncSession
    ):
        """测试发布非草稿合约失败"""
        employer = await _create_user(
            db_session, UserType.EMPLOYER, phone="13800000050"
        )
        headers = _get_auth_headers(employer)
        created = await _create_contract_via_api(client, headers)

        # 第一次发布成功
        await client.post(
            f"/v1/contracts/{created['id']}/publish", headers=headers
        )

        # 第二次发布失败
        resp = await client.post(
            f"/v1/contracts/{created['id']}/publish", headers=headers
        )
        assert resp.status_code == 400

    @pytest.mark.asyncio
    async def test_accept_pending_contract(
        self, client: AsyncClient, db_session: AsyncSession
    ):
        """测试接单成功"""
        employer = await _create_user(
            db_session, UserType.EMPLOYER, phone="13800000051"
        )
        freelancer = await _create_user(
            db_session,
            UserType.FREELANCER,
            phone="13800000052",
            nickname="接单者",
        )
        employer_h = _get_auth_headers(employer)
        freelancer_h = _get_auth_headers(freelancer)

        created = await _create_contract_via_api(client, employer_h)
        await client.post(f"/v1/contracts/{created['id']}/publish", headers=employer_h)

        resp = await client.post(
            f"/v1/contracts/{created['id']}/accept", headers=freelancer_h
        )
        assert resp.status_code == 200
        assert resp.json()["data"]["status"] == "in_progress"

    @pytest.mark.asyncio
    async def test_accept_draft_fails(
        self, client: AsyncClient, db_session: AsyncSession
    ):
        """测试接单草稿合约失败"""
        employer = await _create_user(
            db_session, UserType.EMPLOYER, phone="13800000053"
        )
        freelancer = await _create_user(
            db_session,
            UserType.FREELANCER,
            phone="13800000054",
            nickname="接单者",
        )
        employer_h = _get_auth_headers(employer)
        freelancer_h = _get_auth_headers(freelancer)

        created = await _create_contract_via_api(client, employer_h)

        resp = await client.post(
            f"/v1/contracts/{created['id']}/accept", headers=freelancer_h
        )
        assert resp.status_code == 400

    @pytest.mark.asyncio
    async def test_terminate_contract(
        self, client: AsyncClient, db_session: AsyncSession
    ):
        """测试终止合约"""
        employer = await _create_user(
            db_session, UserType.EMPLOYER, phone="13800000060"
        )
        headers = _get_auth_headers(employer)
        created = await _create_contract_via_api(client, headers)

        resp = await client.post(
            f"/v1/contracts/{created['id']}/terminate", headers=headers
        )
        assert resp.status_code == 200
        assert resp.json()["data"]["status"] == "terminated"

    @pytest.mark.asyncio
    async def test_terminate_completed_fails(
        self, client: AsyncClient, db_session: AsyncSession
    ):
        """测试终止已完成合约失败"""
        employer = await _create_user(
            db_session, UserType.EMPLOYER, phone="13800000061"
        )
        freelancer = await _create_user(
            db_session,
            UserType.FREELANCER,
            phone="13800000062",
            nickname="自由者",
        )
        employer_h = _get_auth_headers(employer)
        freelancer_h = _get_auth_headers(freelancer)

        created = await _create_contract_via_api(client, employer_h)
        # 走完整流程
        await client.post(
            f"/v1/contracts/{created['id']}/publish", headers=employer_h
        )
        await client.post(
            f"/v1/contracts/{created['id']}/accept", headers=freelancer_h
        )
        await client.post(
            f"/v1/contracts/{created['id']}/submit", headers=freelancer_h
        )
        await client.post(
            f"/v1/contracts/{created['id']}/complete", headers=employer_h
        )

        # 终止已完成的合约
        resp = await client.post(
            f"/v1/contracts/{created['id']}/terminate", headers=employer_h
        )
        assert resp.status_code == 400

    @pytest.mark.asyncio
    async def test_only_employer_can_publish(
        self, client: AsyncClient, db_session: AsyncSession
    ):
        """测试只有雇主可以发布"""
        employer = await _create_user(
            db_session, UserType.EMPLOYER, phone="13800000070"
        )
        freelancer = await _create_user(
            db_session,
            UserType.FREELANCER,
            phone="13800000071",
            nickname="自由者",
        )
        employer_h = _get_auth_headers(employer)
        freelancer_h = _get_auth_headers(freelancer)

        created = await _create_contract_via_api(client, employer_h)

        resp = await client.post(
            f"/v1/contracts/{created['id']}/publish", headers=freelancer_h
        )
        assert resp.status_code == 403

    @pytest.mark.asyncio
    async def test_only_freelancer_can_accept(
        self, client: AsyncClient, db_session: AsyncSession
    ):
        """测试只有自由职业者可以接单"""
        employer = await _create_user(
            db_session, UserType.EMPLOYER, phone="13800000072"
        )
        headers = _get_auth_headers(employer)
        created = await _create_contract_via_api(client, headers)
        await client.post(f"/v1/contracts/{created['id']}/publish", headers=headers)

        resp = await client.post(
            f"/v1/contracts/{created['id']}/accept", headers=headers
        )
        assert resp.status_code == 403


# ============================================================
# 交付物清单测试
# ============================================================


class TestDeliverables:
    """交付物清单测试"""

    @pytest.mark.asyncio
    async def test_generate_deliverables_for_development(
        self, client: AsyncClient, db_session: AsyncSession
    ):
        """测试为开发任务生成交付物清单"""
        employer = await _create_user(
            db_session, UserType.EMPLOYER, phone="13800000080"
        )
        headers = _get_auth_headers(employer)
        created = await _create_contract_via_api(client, headers)

        resp = await client.post(
            f"/v1/contracts/{created['id']}/deliverables", headers=headers
        )
        assert resp.status_code == 201
        data = resp.json()["data"]
        # development 类型应该有4个默认交付物
        assert len(data) == 4
        names = [d["name"] for d in data]
        assert "需求文档" in names
        assert "源代码" in names
        assert "测试报告" in names
        assert "部署文档" in names

    @pytest.mark.asyncio
    async def test_generate_deliverables_duplicate_fails(
        self, client: AsyncClient, db_session: AsyncSession
    ):
        """测试重复生成交付物失败"""
        employer = await _create_user(
            db_session, UserType.EMPLOYER, phone="13800000081"
        )
        headers = _get_auth_headers(employer)
        created = await _create_contract_via_api(client, headers)

        # 第一次生成
        await client.post(
            f"/v1/contracts/{created['id']}/deliverables", headers=headers
        )

        # 第二次生成应失败
        resp = await client.post(
            f"/v1/contracts/{created['id']}/deliverables", headers=headers
        )
        assert resp.status_code == 409

    @pytest.mark.asyncio
    async def test_get_deliverables(
        self, client: AsyncClient, db_session: AsyncSession
    ):
        """测试获取交付物列表"""
        employer = await _create_user(
            db_session, UserType.EMPLOYER, phone="13800000082"
        )
        headers = _get_auth_headers(employer)
        created = await _create_contract_via_api(client, headers)

        # 先生成
        await client.post(
            f"/v1/contracts/{created['id']}/deliverables", headers=headers
        )

        # 再查询
        resp = await client.get(
            f"/v1/contracts/{created['id']}/deliverables", headers=headers
        )
        assert resp.status_code == 200
        assert len(resp.json()["data"]) == 4

    @pytest.mark.asyncio
    async def test_get_deliverables_empty(
        self, client: AsyncClient, db_session: AsyncSession
    ):
        """测试获取空交付物列表"""
        employer = await _create_user(
            db_session, UserType.EMPLOYER, phone="13800000083"
        )
        headers = _get_auth_headers(employer)
        created = await _create_contract_via_api(client, headers)

        resp = await client.get(
            f"/v1/contracts/{created['id']}/deliverables", headers=headers
        )
        assert resp.status_code == 200
        assert resp.json()["data"] == []


# ============================================================
# 交付物生成单元测试（纯逻辑）
# ============================================================


class TestDeliverableGeneration:
    """交付物清单生成纯逻辑测试"""

    def test_generate_development_deliverables(self):
        """测试开发类型交付物"""
        result = deliverable_service.generate_deliverables("development")
        assert len(result) == 4
        assert result[0]["name"] == "需求文档"

    def test_generate_design_deliverables(self):
        """测试设计类型交付物"""
        result = deliverable_service.generate_deliverables("design")
        assert len(result) == 3
        names = [d["name"] for d in result]
        assert "设计稿" in names

    def test_generate_copywriting_deliverables(self):
        """测试文案类型交付物"""
        result = deliverable_service.generate_deliverables("copywriting")
        assert len(result) == 3

    def test_generate_translation_deliverables(self):
        """测试翻译类型交付物"""
        result = deliverable_service.generate_deliverables("translation")
        assert len(result) == 3

    def test_generate_data_labeling_deliverables(self):
        """测试数据标注类型交付物"""
        result = deliverable_service.generate_deliverables("data_labeling")
        assert len(result) == 2

    def test_generate_consulting_deliverables(self):
        """测试咨询类型交付物"""
        result = deliverable_service.generate_deliverables("consulting")
        assert len(result) == 2

    def test_generate_other_deliverables(self):
        """测试其他类型交付物"""
        result = deliverable_service.generate_deliverables("other")
        assert len(result) == 1

    def test_generate_with_extra_deliverables(self):
        """测试蓝图中的额外交付物"""
        blueprint = {
            "extra_deliverables": [
                {"name": "API 文档", "required_format": "Swagger"},
            ]
        }
        result = deliverable_service.generate_deliverables("development", blueprint)
        assert len(result) == 5  # 4 默认 + 1 额外
        assert result[4]["name"] == "API 文档"

    def test_generate_invalid_type_fallback(self):
        """测试无效类型回退到 OTHER"""
        result = deliverable_service.generate_deliverables("invalid_type")
        assert len(result) == 1
        assert result[0]["name"] == "交付物"


# ============================================================
# 结算配置测试
# ============================================================


class TestSettlement:
    """结算配置测试"""

    def test_calculate_commission(self):
        """测试佣金计算"""
        result = calculate_commission(Decimal("10000"), Decimal("0.05"))
        assert result == 500.0

    def test_calculate_total_payable(self):
        """测试总应付金额计算"""
        result = calculate_total_payable(
            Decimal("10000"), Decimal("2000"), Decimal("0.05")
        )
        assert result["base_amount"] == 10000.0
        assert result["bonus_amount"] == 2000.0
        assert result["commission"] == 500.0
        assert result["total_payable"] == 11500.0

    def test_validate_settlement_config_valid(self):
        """测试有效结算配置"""
        validate_settlement_config(
            {"base_amount": 10000, "commission_rate": 0.05}
        )

    def test_validate_settlement_config_zero_base(self):
        """测试 base_amount 为0"""
        with pytest.raises(ValueError, match="base_amount 必须大于 0"):
            validate_settlement_config(
                {"base_amount": 0, "commission_rate": 0.05}
            )

    def test_validate_settlement_config_negative_commission(self):
        """测试佣金比例为负"""
        with pytest.raises(ValueError, match="commission_rate 必须在 0 ~ 0.3 之间"):
            validate_settlement_config(
                {"base_amount": 10000, "commission_rate": -0.01}
            )

    def test_validate_settlement_config_high_commission(self):
        """测试佣金比例过高"""
        with pytest.raises(ValueError, match="commission_rate 必须在 0 ~ 0.3 之间"):
            validate_settlement_config(
                {"base_amount": 10000, "commission_rate": 0.35}
            )

    def test_validate_settlement_config_max_commission(self):
        """测试佣金比例上限"""
        validate_settlement_config(
            {"base_amount": 10000, "commission_rate": 0.3}
        )


# ============================================================
# 状态机单元测试（纯逻辑）
# ============================================================


class TestStateMachine:
    """状态机纯逻辑测试"""

    @pytest.mark.asyncio
    async def test_valid_transitions(self, db_session: AsyncSession):
        """测试所有合法的状态转换"""
        employer = await _create_user(
            db_session, UserType.EMPLOYER, phone="13800000090"
        )
        freelancer = await _create_user(
            db_session,
            UserType.FREELANCER,
            phone="13800000091",
            nickname="自由者",
        )

        # draft -> pending
        c = await _create_contract_in_db(
            db_session, employer.id, ContractStatus.DRAFT
        )
        result = await contract_service.publish_contract(db_session, c.id)
        assert result.status == ContractStatus.PENDING

        # pending -> in_progress
        result = await contract_service.accept_contract(
            db_session, c.id, freelancer.id
        )
        assert result.status == ContractStatus.IN_PROGRESS

        # in_progress -> review
        result = await contract_service.submit_for_review(db_session, c.id)
        assert result.status == ContractStatus.REVIEW

        # review -> completed
        result = await contract_service.complete_contract(db_session, c.id)
        assert result.status == ContractStatus.COMPLETED

    @pytest.mark.asyncio
    async def test_invalid_transition_draft_to_completed(
        self, db_session: AsyncSession
    ):
        """测试非法转换：draft -> completed"""
        employer = await _create_user(
            db_session, UserType.EMPLOYER, phone="13800000092"
        )
        c = await _create_contract_in_db(
            db_session, employer.id, ContractStatus.DRAFT
        )

        with pytest.raises(ValueError, match="非法状态转换"):
            await contract_service.complete_contract(db_session, c.id)

    @pytest.mark.asyncio
    async def test_invalid_transition_completed_to_anything(
        self, db_session: AsyncSession
    ):
        """测试终态不可转换"""
        employer = await _create_user(
            db_session, UserType.EMPLOYER, phone="13800000093"
        )
        c = await _create_contract_in_db(
            db_session, employer.id, ContractStatus.COMPLETED
        )

        with pytest.raises(ValueError, match="非法状态转换"):
            await contract_service.terminate_contract(db_session, c.id)

    @pytest.mark.asyncio
    async def test_terminate_from_any_active_state(
        self, db_session: AsyncSession
    ):
        """测试从各种活跃状态终止"""
        employer = await _create_user(
            db_session, UserType.EMPLOYER, phone="13800000094"
        )

        for st in [
            ContractStatus.DRAFT,
            ContractStatus.PENDING,
            ContractStatus.IN_PROGRESS,
            ContractStatus.REVIEW,
        ]:
            c = await _create_contract_in_db(db_session, employer.id, st)
            result = await contract_service.terminate_contract(db_session, c.id)
            assert result.status == ContractStatus.TERMINATED

    @pytest.mark.asyncio
    async def test_review_to_in_progress_reject(
        self, db_session: AsyncSession
    ):
        """测试验收拒绝回到进行中"""
        employer = await _create_user(
            db_session, UserType.EMPLOYER, phone="13800000095"
        )
        c = await _create_contract_in_db(
            db_session, employer.id, ContractStatus.REVIEW
        )

        result = await contract_service.reject_and_resubmit(db_session, c.id)
        assert result.status == ContractStatus.IN_PROGRESS

    @pytest.mark.asyncio
    async def test_review_to_disputed(self, db_session: AsyncSession):
        """测试发起争议"""
        employer = await _create_user(
            db_session, UserType.EMPLOYER, phone="13800000096"
        )
        c = await _create_contract_in_db(
            db_session, employer.id, ContractStatus.REVIEW
        )

        result = await contract_service.dispute_contract(db_session, c.id)
        assert result.status == ContractStatus.DISPUTED


# ============================================================
# 合约编号生成测试
# ============================================================


class TestContractNoGeneration:
    """合约编号格式测试"""

    def test_contract_no_format(self):
        """测试合约编号格式 OW-YYYYMMDD-XXXX"""
        from app.modules.contract.service import _generate_contract_no

        no = _generate_contract_no()
        assert no.startswith("OW-")
        parts = no.split("-")
        assert len(parts) == 3
        assert len(parts[1]) == 8  # YYYYMMDD
        assert len(parts[2]) == 4  # XXXX
        assert parts[2].isdigit()
