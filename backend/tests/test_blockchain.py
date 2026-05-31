"""
链上存证模块完整单元测试
覆盖：
- 存证记录创建（各节点类型）
- 存证记录查询（单条、按合约查询）
- 存证记录验证（内容一致、内容篡改）
- 权限校验
"""

from __future__ import annotations

import uuid

import pytest
import pytest_asyncio
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.security import create_access_token, hash_password
from app.models.blockchain import BlockchainRecord, NodeType
from app.models.user import User, UserStatus, UserType
from app.modules.blockchain import service as blockchain_service


# ============================================================
# 辅助函数
# ============================================================


async def _create_user(
    db: AsyncSession,
    user_type: UserType = UserType.ADMIN,
    phone: str = "13800000099",
    nickname: str = "测试管理",
) -> User:
    """创建测试用户"""
    user = User(
        phone=phone,
        nickname=nickname,
        user_type=user_type,
        hashed_password=hash_password("TestPass123"),
        status=UserStatus.ACTIVE,
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


def _sample_content_data() -> dict:
    """样本存证内容数据"""
    return {
        "contract_id": str(uuid.uuid4()),
        "title": "测试合约",
        "amount": "10000.00",
        "timestamp": "2026-01-01T00:00:00Z",
    }


# ============================================================
# Service 层单元测试
# ============================================================


class TestBlockchainService:
    """链上存证 Service 层测试"""

    @pytest.mark.asyncio
    async def test_create_record(self, db_session: AsyncSession):
        """测试创建存证记录"""
        contract_id = uuid.uuid4()
        content_data = _sample_content_data()

        record = await blockchain_service.create_record(
            db=db_session,
            contract_id=contract_id,
            node_type=NodeType.CONTRACT_CREATED,
            content_data=content_data,
        )

        assert record.id is not None
        assert record.contract_id == contract_id
        assert record.node_type == NodeType.CONTRACT_CREATED
        assert len(record.content_hash) == 64  # SHA-256 hex
        assert len(record.block_hash) == 64
        assert record.block_height is not None
        assert record.block_height >= 1_000_000
        assert record.timestamp is not None

    @pytest.mark.asyncio
    async def test_create_record_different_node_types(self, db_session: AsyncSession):
        """测试不同节点类型的存证创建"""
        contract_id = uuid.uuid4()
        content_data = _sample_content_data()

        node_types = [
            NodeType.CONTRACT_CREATED,
            NodeType.DELIVERABLE_SUBMIT,
            NodeType.ACCEPTANCE_CONFIRM,
            NodeType.TRANSACTION_COMPLETE,
        ]

        for nt in node_types:
            record = await blockchain_service.create_record(
                db=db_session,
                contract_id=contract_id,
                node_type=nt,
                content_data=content_data,
            )
            assert record.node_type == nt

    @pytest.mark.asyncio
    async def test_verify_record_valid(self, db_session: AsyncSession):
        """测试存证验证 - 内容一致"""
        contract_id = uuid.uuid4()
        content_data = _sample_content_data()

        record = await blockchain_service.create_record(
            db=db_session,
            contract_id=contract_id,
            node_type=NodeType.CONTRACT_CREATED,
            content_data=content_data,
        )

        is_valid = await blockchain_service.verify_record(
            db=db_session,
            record_id=record.id,
            content_data=content_data,
        )
        assert is_valid is True

    @pytest.mark.asyncio
    async def test_verify_record_tampered(self, db_session: AsyncSession):
        """测试存证验证 - 内容被篡改"""
        contract_id = uuid.uuid4()
        content_data = _sample_content_data()

        record = await blockchain_service.create_record(
            db=db_session,
            contract_id=contract_id,
            node_type=NodeType.CONTRACT_CREATED,
            content_data=content_data,
        )

        tampered_data = {**content_data, "amount": "99999.99"}
        is_valid = await blockchain_service.verify_record(
            db=db_session,
            record_id=record.id,
            content_data=tampered_data,
        )
        assert is_valid is False

    @pytest.mark.asyncio
    async def test_verify_record_not_found(self, db_session: AsyncSession):
        """测试验证不存在的存证记录"""
        with pytest.raises(ValueError, match="存证记录不存在"):
            await blockchain_service.verify_record(
                db=db_session,
                record_id=uuid.uuid4(),
                content_data=_sample_content_data(),
            )

    @pytest.mark.asyncio
    async def test_get_record(self, db_session: AsyncSession):
        """测试获取单条存证记录"""
        contract_id = uuid.uuid4()
        record = await blockchain_service.create_record(
            db=db_session,
            contract_id=contract_id,
            node_type=NodeType.CONTRACT_CREATED,
            content_data=_sample_content_data(),
        )

        fetched = await blockchain_service.get_record(db=db_session, record_id=record.id)
        assert fetched.id == record.id
        assert fetched.contract_id == contract_id

    @pytest.mark.asyncio
    async def test_get_record_not_found(self, db_session: AsyncSession):
        """测试获取不存在的存证记录"""
        with pytest.raises(ValueError, match="存证记录不存在"):
            await blockchain_service.get_record(db=db_session, record_id=uuid.uuid4())

    @pytest.mark.asyncio
    async def test_get_records_by_contract(self, db_session: AsyncSession):
        """测试按合约查询存证记录列表"""
        contract_id = uuid.uuid4()

        # 创建3条不同节点类型的存证
        for nt in [
            NodeType.CONTRACT_CREATED,
            NodeType.DELIVERABLE_SUBMIT,
            NodeType.ACCEPTANCE_CONFIRM,
        ]:
            await blockchain_service.create_record(
                db=db_session,
                contract_id=contract_id,
                node_type=nt,
                content_data=_sample_content_data(),
            )

        records = await blockchain_service.get_records_by_contract(
            db=db_session, contract_id=contract_id
        )
        assert len(records) == 3

    @pytest.mark.asyncio
    async def test_get_records_by_contract_empty(self, db_session: AsyncSession):
        """测试查询无存证的合约"""
        records = await blockchain_service.get_records_by_contract(
            db=db_session, contract_id=uuid.uuid4()
        )
        assert len(records) == 0

    @pytest.mark.asyncio
    async def test_content_hash_deterministic(self, db_session: AsyncSession):
        """测试相同内容产生相同哈希"""
        content_data = _sample_content_data()
        hash1 = blockchain_service._compute_content_hash(content_data)
        hash2 = blockchain_service._compute_content_hash(content_data)
        assert hash1 == hash2

    @pytest.mark.asyncio
    async def test_content_hash_order_independent(self, db_session: AsyncSession):
        """测试哈希计算与字段顺序无关"""
        data1 = {"a": 1, "b": 2}
        data2 = {"b": 2, "a": 1}
        assert blockchain_service._compute_content_hash(data1) == blockchain_service._compute_content_hash(data2)

    @pytest.mark.asyncio
    async def test_record_contract_created_shortcut(self, db_session: AsyncSession):
        """测试合约创建存证快捷方法"""
        contract_id = uuid.uuid4()
        record = await blockchain_service.record_contract_created(
            db=db_session,
            contract_id=contract_id,
            content_data=_sample_content_data(),
        )
        assert record.node_type == NodeType.CONTRACT_CREATED

    @pytest.mark.asyncio
    async def test_record_deliverable_submit_shortcut(self, db_session: AsyncSession):
        """测试交付物提交存证快捷方法"""
        contract_id = uuid.uuid4()
        record = await blockchain_service.record_deliverable_submit(
            db=db_session,
            contract_id=contract_id,
            content_data=_sample_content_data(),
        )
        assert record.node_type == NodeType.DELIVERABLE_SUBMIT

    @pytest.mark.asyncio
    async def test_record_acceptance_confirm_shortcut(self, db_session: AsyncSession):
        """测试验收确认存证快捷方法"""
        contract_id = uuid.uuid4()
        record = await blockchain_service.record_acceptance_confirm(
            db=db_session,
            contract_id=contract_id,
            content_data=_sample_content_data(),
        )
        assert record.node_type == NodeType.ACCEPTANCE_CONFIRM

    @pytest.mark.asyncio
    async def test_record_transaction_complete_shortcut(self, db_session: AsyncSession):
        """测试交易完成存证快捷方法"""
        contract_id = uuid.uuid4()
        record = await blockchain_service.record_transaction_complete(
            db=db_session,
            contract_id=contract_id,
            content_data=_sample_content_data(),
        )
        assert record.node_type == NodeType.TRANSACTION_COMPLETE

    @pytest.mark.asyncio
    async def test_record_dispute_initiated_shortcut(self, db_session: AsyncSession):
        """测试争议发起存证快捷方法"""
        contract_id = uuid.uuid4()
        record = await blockchain_service.record_dispute_initiated(
            db=db_session,
            contract_id=contract_id,
            content_data=_sample_content_data(),
        )
        assert record.node_type == NodeType.DISPUTE_INITIATED


# ============================================================
# API 端点集成测试
# ============================================================


class TestBlockchainAPI:
    """链上存证 API 端点测试"""

    @pytest.mark.asyncio
    async def test_create_record_api(
        self, client: AsyncClient, db_session: AsyncSession
    ):
        """测试 POST /v1/blockchain/record"""
        admin = await _create_user(db_session)
        headers = _get_auth_headers(admin)

        contract_id = str(uuid.uuid4())
        payload = {
            "contract_id": contract_id,
            "node_type": "contract_created",
            "content_data": _sample_content_data(),
        }

        resp = await client.post("/v1/blockchain/record", json=payload, headers=headers)
        assert resp.status_code == 201
        data = resp.json()
        assert data["code"] == 201
        assert data["data"]["contract_id"] == contract_id
        assert data["data"]["node_type"] == "contract_created"
        assert len(data["data"]["content_hash"]) == 64
        assert len(data["data"]["block_hash"]) == 64

    @pytest.mark.asyncio
    async def test_get_record_api(
        self, client: AsyncClient, db_session: AsyncSession
    ):
        """测试 GET /v1/blockchain/records/{record_id}"""
        admin = await _create_user(db_session)
        headers = _get_auth_headers(admin)

        # 先创建存证
        contract_id = str(uuid.uuid4())
        payload = {
            "contract_id": contract_id,
            "node_type": "deliverable_submit",
            "content_data": _sample_content_data(),
        }
        create_resp = await client.post(
            "/v1/blockchain/record", json=payload, headers=headers
        )
        record_id = create_resp.json()["data"]["id"]

        # 查询存证
        resp = await client.get(
            f"/v1/blockchain/records/{record_id}", headers=headers
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["data"]["id"] == record_id
        assert data["data"]["node_type"] == "deliverable_submit"

    @pytest.mark.asyncio
    async def test_get_record_not_found_api(
        self, client: AsyncClient, db_session: AsyncSession
    ):
        """测试查询不存在的存证记录"""
        admin = await _create_user(db_session)
        headers = _get_auth_headers(admin)

        fake_id = str(uuid.uuid4())
        resp = await client.get(
            f"/v1/blockchain/records/{fake_id}", headers=headers
        )
        assert resp.status_code == 404

    @pytest.mark.asyncio
    async def test_verify_record_api(
        self, client: AsyncClient, db_session: AsyncSession
    ):
        """测试 POST /v1/blockchain/records/{record_id}/verify"""
        admin = await _create_user(db_session)
        headers = _get_auth_headers(admin)

        content_data = _sample_content_data()

        # 创建存证
        payload = {
            "contract_id": str(uuid.uuid4()),
            "node_type": "acceptance_confirm",
            "content_data": content_data,
        }
        create_resp = await client.post(
            "/v1/blockchain/record", json=payload, headers=headers
        )
        record_id = create_resp.json()["data"]["id"]

        # 验证（内容一致）
        verify_payload = {"content_data": content_data}
        resp = await client.post(
            f"/v1/blockchain/records/{record_id}/verify",
            json=verify_payload,
            headers=headers,
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["data"]["is_valid"] is True

    @pytest.mark.asyncio
    async def test_verify_record_tampered_api(
        self, client: AsyncClient, db_session: AsyncSession
    ):
        """测试验证被篡改的存证"""
        admin = await _create_user(db_session)
        headers = _get_auth_headers(admin)

        content_data = _sample_content_data()

        # 创建存证
        payload = {
            "contract_id": str(uuid.uuid4()),
            "node_type": "transaction_complete",
            "content_data": content_data,
        }
        create_resp = await client.post(
            "/v1/blockchain/record", json=payload, headers=headers
        )
        record_id = create_resp.json()["data"]["id"]

        # 验证（内容被篡改）
        tampered = {**content_data, "amount": "0.01"}
        resp = await client.post(
            f"/v1/blockchain/records/{record_id}/verify",
            json={"content_data": tampered},
            headers=headers,
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["data"]["is_valid"] is False

    @pytest.mark.asyncio
    async def test_list_records_by_contract_api(
        self, client: AsyncClient, db_session: AsyncSession
    ):
        """测试 GET /v1/blockchain/contracts/{contract_id}/records"""
        admin = await _create_user(db_session)
        headers = _get_auth_headers(admin)
        contract_id = str(uuid.uuid4())

        # 创建2条存证
        for nt in ["contract_created", "deliverable_submit"]:
            payload = {
                "contract_id": contract_id,
                "node_type": nt,
                "content_data": _sample_content_data(),
            }
            await client.post("/v1/blockchain/record", json=payload, headers=headers)

        # 查询合约存证列表
        resp = await client.get(
            f"/v1/blockchain/contracts/{contract_id}/records", headers=headers
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["data"]["total"] == 2
        assert len(data["data"]["items"]) == 2

    @pytest.mark.asyncio
    async def test_create_record_unauthorized(self, client: AsyncClient):
        """测试未认证创建存证（无 token 时返回 401 或请求被拒绝）"""
        payload = {
            "contract_id": str(uuid.uuid4()),
            "node_type": "contract_created",
            "content_data": _sample_content_data(),
        }
        resp = await client.post("/v1/blockchain/record", json=payload)
        # 根据中间件配置，无 token 时可能返回 401 或 403
        assert resp.status_code in (401, 403)

    @pytest.mark.asyncio
    async def test_freelancer_can_create_record(
        self, client: AsyncClient, db_session: AsyncSession
    ):
        """测试 freelancer 角色可以创建存证（有 BLOCKCHAIN_RECORD 权限）"""
        freelancer = await _create_user(
            db_session,
            user_type=UserType.FREELANCER,
            phone="13800000088",
            nickname="测试自由职业者",
        )
        headers = _get_auth_headers(freelancer)

        payload = {
            "contract_id": str(uuid.uuid4()),
            "node_type": "contract_created",
            "content_data": _sample_content_data(),
        }
        resp = await client.post("/v1/blockchain/record", json=payload, headers=headers)
        assert resp.status_code == 201
