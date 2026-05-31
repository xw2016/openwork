"""
验收模块完整单元测试

覆盖：
- AI 验收引擎（规则引擎模拟）
  - 格式匹配检查
  - 文件完整性检查
  - 内容要素覆盖检查
  - 整体结果判定
- 验收报告生成
- 验收服务
  - 合约验收（全部通过/部分拒绝）
  - 拒绝交付物
  - 重提交付物（含超过最大修改次数）
  - 验收记录查询
- 路由端点
  - 触发验收
  - 验收记录列表/详情
  - 拒绝/重提交付物
"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone
from decimal import Decimal
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
import pytest_asyncio
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.security import hash_password, create_access_token
from app.models.acceptance import AcceptanceRecord, AcceptanceResult
from app.models.contract import Contract, ContractStatus, TaskType
from app.models.deliverable import AcceptanceStatus, Deliverable
from app.models.user import User, UserStatus, UserType
from app.modules.acceptance.engine import (
    AcceptanceEngine,
    CheckItem,
    EvaluationResult,
    generate_report,
)
from app.modules.acceptance import service as acceptance_service


# ============================================================
# 辅助函数
# ============================================================


async def _create_user(
    db: AsyncSession,
    user_type: UserType = UserType.EMPLOYER,
    phone: str = "13900000001",
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


def _get_auth_headers(user: User) -> dict:
    """获取认证 headers"""
    token = create_access_token(
        data={"sub": str(user.id), "type": "access", "role": user.user_type.value}
    )
    return {"Authorization": f"Bearer {token}"}


async def _create_contract_in_db(
    db: AsyncSession,
    employer_id: uuid.UUID,
    status: ContractStatus = ContractStatus.REVIEW,
    freelancer_id: uuid.UUID = None,
) -> Contract:
    """直接在数据库中创建合约"""
    contract = Contract(
        contract_no=f"OW-TEST-{uuid.uuid4().hex[:8]}",
        employer_id=employer_id,
        freelancer_id=freelancer_id,
        title="验收测试合约",
        task_type=TaskType.DEVELOPMENT,
        intent_blueprint={"requirements": "实现用户管理模块"},
        deliverables=[],
        base_amount=Decimal("10000.00"),
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
    required_format: str = "Git 仓库",
    acceptance_criteria: dict = None,
    file_url: str = "https://example.com/repo.git",
    file_hash: str = "a1b2c3d4e5f6a1b2c3d4e5f6a1b2c3d4e5f6a1b2c3d4e5f6a1b2c3d4e5f6a1b2",
    submit_version: int = 1,
    acceptance_status: AcceptanceStatus = AcceptanceStatus.PENDING,
) -> Deliverable:
    """直接在数据库中创建交付物"""
    deliverable = Deliverable(
        contract_id=contract_id,
        deliverable_index=1,
        name=name,
        required_format=required_format,
        acceptance_criteria=acceptance_criteria or {"description": "符合编码规范"},
        file_url=file_url,
        file_hash=file_hash,
        submit_version=submit_version,
        submit_time=datetime.now(timezone.utc),
        acceptance_status=acceptance_status,
    )
    db.add(deliverable)
    await db.commit()
    await db.refresh(deliverable)
    return deliverable


# ============================================================
# 验收引擎测试
# ============================================================


class TestAcceptanceEngine:
    """验收引擎核心测试"""

    def test_engine_format_check_pass(self):
        """测试格式匹配检查 - 通过"""
        engine = AcceptanceEngine()
        deliverable = MagicMock()
        deliverable.id = uuid.uuid4()
        deliverable.name = "源代码"
        deliverable.required_format = "Git 仓库"
        deliverable.file_url = "https://github.com/user/repo.git"
        deliverable.file_hash = "a1b2c3d4e5f6a1b2c3d4e5f6a1b2c3d4"
        deliverable.acceptance_criteria = {"description": "符合编码规范"}
        deliverable.acceptance_result = None

        result = engine.evaluate_deliverable(deliverable)
        assert result.overall == "approved"

    def test_engine_format_check_fail(self):
        """测试格式匹配检查 - 失败（格式不匹配）"""
        engine = AcceptanceEngine()
        deliverable = MagicMock()
        deliverable.id = uuid.uuid4()
        deliverable.name = "需求文档"
        deliverable.required_format = "PDF"
        deliverable.file_url = "https://example.com/doc.txt"
        deliverable.file_hash = "a1b2c3d4e5f6a1b2c3d4e5f6a1b2c3d4"
        deliverable.acceptance_criteria = {"description": "完整的需求描述"}
        deliverable.acceptance_result = None

        result = engine.evaluate_deliverable(deliverable)
        # TXT 文件不符合 PDF 要求
        assert result.overall == "rejected"
        format_items = [i for i in result.items if i.name == "格式匹配"]
        assert len(format_items) == 1
        assert format_items[0].status == "fail"

    def test_engine_no_file_url(self):
        """测试文件 URL 缺失"""
        engine = AcceptanceEngine()
        deliverable = MagicMock()
        deliverable.id = uuid.uuid4()
        deliverable.name = "测试报告"
        deliverable.required_format = "PDF"
        deliverable.file_url = None
        deliverable.file_hash = None
        deliverable.acceptance_criteria = {"description": "测试报告"}
        deliverable.acceptance_result = None

        result = engine.evaluate_deliverable(deliverable)
        assert result.overall == "rejected"
        url_items = [i for i in result.items if i.name == "文件上传"]
        assert len(url_items) == 1
        assert url_items[0].status == "fail"

    def test_engine_no_file_hash(self):
        """测试文件哈希缺失"""
        engine = AcceptanceEngine()
        deliverable = MagicMock()
        deliverable.id = uuid.uuid4()
        deliverable.name = "测试报告"
        deliverable.required_format = "PDF"
        deliverable.file_url = "https://example.com/report.pdf"
        deliverable.file_hash = None
        deliverable.acceptance_criteria = {"description": "测试报告"}
        deliverable.acceptance_result = None

        result = engine.evaluate_deliverable(deliverable)
        assert result.overall == "rejected"
        hash_items = [i for i in result.items if i.name == "文件哈希"]
        assert len(hash_items) == 1
        assert hash_items[0].status == "fail"

    def test_engine_no_format_requirement(self):
        """测试未指定格式要求时默认通过"""
        engine = AcceptanceEngine()
        deliverable = MagicMock()
        deliverable.id = uuid.uuid4()
        deliverable.name = "交付物"
        deliverable.required_format = None
        deliverable.file_url = "https://example.com/file.dat"
        deliverable.file_hash = "a1b2c3d4e5f6a1b2c3d4e5f6a1b2c3d4"
        deliverable.acceptance_criteria = {"description": "按要求交付"}
        deliverable.acceptance_result = None

        result = engine.evaluate_deliverable(deliverable)
        assert result.overall == "approved"

    def test_engine_content_criteria_with_description(self):
        """测试内容要素覆盖检查（描述性标准）"""
        engine = AcceptanceEngine()
        deliverable = MagicMock()
        deliverable.id = uuid.uuid4()
        deliverable.name = "源代码"
        deliverable.required_format = "Git 仓库"
        deliverable.file_url = "https://github.com/user/repo.git"
        deliverable.file_hash = "a1b2c3d4e5f6a1b2c3d4e5f6a1b2c3d4"
        deliverable.acceptance_criteria = {
            "description": "包含完整的需求描述和验收标准"
        }
        deliverable.acceptance_result = None

        result = engine.evaluate_deliverable(deliverable)
        assert result.overall == "approved"
        content_items = [i for i in result.items if "内容要素覆盖" in i.name]
        assert len(content_items) >= 1
        assert content_items[0].status == "pass"

    def test_engine_empty_criteria(self):
        """测试空验收标准"""
        engine = AcceptanceEngine()
        deliverable = MagicMock()
        deliverable.id = uuid.uuid4()
        deliverable.name = "交付物"
        deliverable.required_format = None
        deliverable.file_url = "https://example.com/file.dat"
        deliverable.file_hash = "a1b2c3d4e5f6a1b2c3d4e5f6a1b2c3d4"
        deliverable.acceptance_criteria = {}
        deliverable.acceptance_result = None

        result = engine.evaluate_deliverable(deliverable)
        assert result.overall == "approved"

    def test_engine_pdf_format_pass(self):
        """测试 PDF 格式匹配通过"""
        engine = AcceptanceEngine()
        deliverable = MagicMock()
        deliverable.id = uuid.uuid4()
        deliverable.name = "需求文档"
        deliverable.required_format = "PDF/DOCX"
        deliverable.file_url = "https://example.com/doc.pdf"
        deliverable.file_hash = "a1b2c3d4e5f6a1b2c3d4e5f6a1b2c3d4"
        deliverable.acceptance_criteria = {"description": "需求文档"}
        deliverable.acceptance_result = None

        result = engine.evaluate_deliverable(deliverable)
        assert result.overall == "approved"

    def test_engine_docx_format_pass(self):
        """测试 DOCX 格式匹配通过（PDF/DOCX 允许）"""
        engine = AcceptanceEngine()
        deliverable = MagicMock()
        deliverable.id = uuid.uuid4()
        deliverable.name = "需求文档"
        deliverable.required_format = "PDF/DOCX"
        deliverable.file_url = "https://example.com/doc.docx"
        deliverable.file_hash = "a1b2c3d4e5f6a1b2c3d4e5f6a1b2c3d4"
        deliverable.acceptance_criteria = {"description": "需求文档"}
        deliverable.acceptance_result = None

        result = engine.evaluate_deliverable(deliverable)
        assert result.overall == "approved"

    def test_engine_invalid_hash_format(self):
        """测试无效哈希格式"""
        engine = AcceptanceEngine()
        deliverable = MagicMock()
        deliverable.id = uuid.uuid4()
        deliverable.name = "交付物"
        deliverable.required_format = None
        deliverable.file_url = "https://example.com/file.dat"
        deliverable.file_hash = "invalid-hash"
        deliverable.acceptance_criteria = {"description": "按要求交付"}
        deliverable.acceptance_result = None

        result = engine.evaluate_deliverable(deliverable)
        assert result.overall == "rejected"
        hash_items = [i for i in result.items if i.name == "文件哈希"]
        assert hash_items[0].status == "fail"


# ============================================================
# 验收报告生成测试
# ============================================================


class TestGenerateReport:
    """验收报告生成测试"""

    def test_approved_report(self):
        """测试通过时的报告生成"""
        deliverable = MagicMock()
        deliverable.name = "源代码"

        eval_result = EvaluationResult(
            deliverable_id=uuid.uuid4(),
            overall="approved",
            items=[
                CheckItem("格式匹配", "pass", "符合要求"),
                CheckItem("文件上传", "pass", "已上传"),
                CheckItem("文件哈希", "pass", "已提供"),
            ],
        )

        report = generate_report(deliverable, eval_result)
        report_dict = report.to_dict()

        assert "验收通过" in report_dict["summary"]
        assert report_dict["total_checks"] == 3
        assert report_dict["passed"] == 3
        assert report_dict["failed"] == 0
        assert len(report_dict["items"]) == 3
        assert "timestamp" in report_dict

    def test_rejected_report(self):
        """测试拒绝时的报告生成"""
        deliverable = MagicMock()
        deliverable.name = "需求文档"

        eval_result = EvaluationResult(
            deliverable_id=uuid.uuid4(),
            overall="rejected",
            items=[
                CheckItem("格式匹配", "fail", "格式不匹配"),
                CheckItem("文件上传", "pass", "已上传"),
                CheckItem("文件哈希", "pass", "已提供"),
            ],
        )

        report = generate_report(deliverable, eval_result)
        report_dict = report.to_dict()

        assert "验收未通过" in report_dict["summary"]
        assert report_dict["total_checks"] == 3
        assert report_dict["passed"] == 2
        assert report_dict["failed"] == 1

    def test_report_structure(self):
        """测试报告结构完整性"""
        deliverable = MagicMock()
        deliverable.name = "测试报告"

        eval_result = EvaluationResult(
            deliverable_id=uuid.uuid4(),
            overall="approved",
            items=[
                CheckItem("格式匹配", "pass", "PDF 格式正确", required=True),
                CheckItem("内容覆盖", "pass", "满足要求", required=False),
            ],
        )

        report = generate_report(deliverable, eval_result)
        report_dict = report.to_dict()

        # 验证报告结构
        assert "summary" in report_dict
        assert "total_checks" in report_dict
        assert "passed" in report_dict
        assert "failed" in report_dict
        assert "items" in report_dict
        assert "timestamp" in report_dict

        # 验证每项结构
        for item in report_dict["items"]:
            assert "name" in item
            assert "status" in item
            assert "detail" in item
            assert "required" in item


# ============================================================
# 验收服务测试（数据库级）
# ============================================================


class TestAcceptanceService:
    """验收服务测试"""

    @pytest.mark.asyncio
    async def test_evaluate_contract_all_approved(self, db_session: AsyncSession):
        """测试合约验收 - 全部通过"""
        employer = await _create_user(db_session, UserType.EMPLOYER, phone="13900000101")
        contract = await _create_contract_in_db(
            db_session, employer.id, status=ContractStatus.REVIEW
        )
        # 创建两个交付物，都已提交
        await _create_deliverable_in_db(
            db_session, contract.id,
            name="需求文档",
            required_format="PDF",
            file_url="https://example.com/doc.pdf",
            file_hash="a1b2c3d4e5f6a1b2c3d4e5f6a1b2c3d4e5f6a1b2c3d4e5f6a1b2c3d4e5f6a1b2",
        )
        await _create_deliverable_in_db(
            db_session, contract.id,
            name="源代码",
            required_format="Git 仓库",
            file_url="https://github.com/user/repo.git",
            file_hash="b2c3d4e5f6a1b2c3d4e5f6a1b2c3d4e5f6a1b2c3d4e5f6a1b2c3d4e5f6a1b2c3",
        )

        records = await acceptance_service.evaluate_contract(db_session, contract.id)

        assert len(records) == 2
        # 刷新合约状态
        await db_session.refresh(contract)
        assert contract.status == ContractStatus.COMPLETED

    @pytest.mark.asyncio
    async def test_evaluate_contract_some_rejected(self, db_session: AsyncSession):
        """测试合约验收 - 部分拒绝"""
        employer = await _create_user(db_session, UserType.EMPLOYER, phone="13900000102")
        contract = await _create_contract_in_db(
            db_session, employer.id, status=ContractStatus.REVIEW
        )
        # 一个交付物格式不匹配（PDF 要求但上传了 TXT）
        await _create_deliverable_in_db(
            db_session, contract.id,
            name="需求文档",
            required_format="PDF",
            file_url="https://example.com/doc.txt",
            file_hash="a1b2c3d4e5f6a1b2c3d4e5f6a1b2c3d4e5f6a1b2c3d4e5f6a1b2c3d4e5f6a1b2",
        )

        records = await acceptance_service.evaluate_contract(db_session, contract.id)

        assert len(records) == 1
        assert records[0].result == AcceptanceResult.REJECTED
        await db_session.refresh(contract)
        assert contract.status == ContractStatus.IN_PROGRESS

    @pytest.mark.asyncio
    async def test_evaluate_contract_not_in_review(self, db_session: AsyncSession):
        """测试非 review 状态合约验收失败"""
        employer = await _create_user(db_session, UserType.EMPLOYER, phone="13900000103")
        contract = await _create_contract_in_db(
            db_session, employer.id, status=ContractStatus.DRAFT
        )

        with pytest.raises(ValueError, match="review"):
            await acceptance_service.evaluate_contract(db_session, contract.id)

    @pytest.mark.asyncio
    async def test_evaluate_contract_no_deliverables(self, db_session: AsyncSession):
        """测试无交付物合约验收失败"""
        employer = await _create_user(db_session, UserType.EMPLOYER, phone="13900000104")
        contract = await _create_contract_in_db(
            db_session, employer.id, status=ContractStatus.REVIEW
        )

        with pytest.raises(ValueError, match="没有已提交的交付物"):
            await acceptance_service.evaluate_contract(db_session, contract.id)

    @pytest.mark.asyncio
    async def test_reject_deliverable(self, db_session: AsyncSession):
        """测试拒绝交付物"""
        employer = await _create_user(db_session, UserType.EMPLOYER, phone="13900000105")
        contract = await _create_contract_in_db(
            db_session, employer.id, status=ContractStatus.REVIEW
        )
        deliverable = await _create_deliverable_in_db(db_session, contract.id)

        record = await acceptance_service.reject_deliverable(
            db_session, deliverable.id, "代码质量不达标"
        )

        assert record.result == AcceptanceResult.REJECTED
        assert "代码质量不达标" in record.acceptance_report.get("rejection_reason", "")
        await db_session.refresh(deliverable)
        assert deliverable.acceptance_status == AcceptanceStatus.REJECTED
        await db_session.refresh(contract)
        assert contract.status == ContractStatus.IN_PROGRESS

    @pytest.mark.asyncio
    async def test_reject_deliverable_not_found(self, db_session: AsyncSession):
        """测试拒绝不存在的交付物"""
        with pytest.raises(ValueError, match="交付物不存在"):
            await acceptance_service.reject_deliverable(
                db_session, uuid.uuid4(), "原因"
            )

    @pytest.mark.asyncio
    async def test_resubmit_deliverable(self, db_session: AsyncSession):
        """测试重提交付物"""
        employer = await _create_user(db_session, UserType.EMPLOYER, phone="13900000106")
        contract = await _create_contract_in_db(
            db_session, employer.id, status=ContractStatus.IN_PROGRESS
        )
        deliverable = await _create_deliverable_in_db(
            db_session, contract.id,
            acceptance_status=AcceptanceStatus.REJECTED,
            submit_version=1,
        )

        updated = await acceptance_service.resubmit_deliverable(
            db_session,
            deliverable.id,
            "https://example.com/new_doc.pdf",
            "c3d4e5f6a1b2c3d4e5f6a1b2c3d4e5f6a1b2c3d4e5f6a1b2c3d4e5f6a1b2c3d4",
        )

        assert updated.submit_version == 2
        assert updated.acceptance_status == AcceptanceStatus.PENDING
        assert updated.file_url == "https://example.com/new_doc.pdf"
        await db_session.refresh(contract)
        assert contract.status == ContractStatus.REVIEW

    @pytest.mark.asyncio
    async def test_resubmit_deliverable_exceeds_max(self, db_session: AsyncSession):
        """测试超过最大修改次数的重提"""
        employer = await _create_user(db_session, UserType.EMPLOYER, phone="13900000107")
        contract = await _create_contract_in_db(
            db_session, employer.id, status=ContractStatus.IN_PROGRESS
        )
        # 设置提交版本为 MAX_RESUBMIT（再提交就会超过）
        deliverable = await _create_deliverable_in_db(
            db_session, contract.id,
            acceptance_status=AcceptanceStatus.REJECTED,
            submit_version=acceptance_service.MAX_RESUBMIT,
        )

        updated = await acceptance_service.resubmit_deliverable(
            db_session,
            deliverable.id,
            "https://example.com/new_doc.pdf",
            "c3d4e5f6a1b2c3d4e5f6a1b2c3d4e5f6a1b2c3d4e5f6a1b2c3d4e5f6a1b2c3d4",
        )

        assert updated.submit_version == acceptance_service.MAX_RESUBMIT + 1
        # 验证标记了需要人工审核
        assert updated.acceptance_result is not None
        assert updated.acceptance_result.get("needs_manual_review") is True

    @pytest.mark.asyncio
    async def test_resubmit_deliverable_wrong_status(self, db_session: AsyncSession):
        """测试非拒绝状态交付物重提失败"""
        employer = await _create_user(db_session, UserType.EMPLOYER, phone="13900000108")
        contract = await _create_contract_in_db(
            db_session, employer.id, status=ContractStatus.IN_PROGRESS
        )
        deliverable = await _create_deliverable_in_db(
            db_session, contract.id,
            acceptance_status=AcceptanceStatus.APPROVED,
        )

        with pytest.raises(ValueError, match="只有被拒绝"):
            await acceptance_service.resubmit_deliverable(
                db_session,
                deliverable.id,
                "https://example.com/new.pdf",
                "c3d4e5f6a1b2c3d4e5f6a1b2c3d4e5f6a1b2c3d4e5f6a1b2c3d4e5f6a1b2c3d4",
            )

    @pytest.mark.asyncio
    async def test_get_acceptance_records(self, db_session: AsyncSession):
        """测试获取验收记录列表"""
        employer = await _create_user(db_session, UserType.EMPLOYER, phone="13900000109")
        contract = await _create_contract_in_db(
            db_session, employer.id, status=ContractStatus.REVIEW
        )
        await _create_deliverable_in_db(
            db_session, contract.id,
            name="源代码",
            required_format="Git 仓库",
            file_url="https://github.com/user/repo.git",
            file_hash="a1b2c3d4e5f6a1b2c3d4e5f6a1b2c3d4e5f6a1b2c3d4e5f6a1b2c3d4e5f6a1b2",
        )

        # 先执行一次验收
        records = await acceptance_service.evaluate_contract(db_session, contract.id)
        assert len(records) > 0

        # 查询验收记录
        fetched = await acceptance_service.get_acceptance_records(db_session, contract.id)
        assert len(fetched) == len(records)

    @pytest.mark.asyncio
    async def test_get_acceptance_record_detail(self, db_session: AsyncSession):
        """测试获取单个验收记录详情"""
        employer = await _create_user(db_session, UserType.EMPLOYER, phone="13900000110")
        contract = await _create_contract_in_db(
            db_session, employer.id, status=ContractStatus.REVIEW
        )
        await _create_deliverable_in_db(
            db_session, contract.id,
            name="源代码",
            required_format="Git 仓库",
            file_url="https://github.com/user/repo.git",
            file_hash="a1b2c3d4e5f6a1b2c3d4e5f6a1b2c3d4e5f6a1b2c3d4e5f6a1b2c3d4e5f6a1b2",
        )

        records = await acceptance_service.evaluate_contract(db_session, contract.id)
        record_id = records[0].id

        detail = await acceptance_service.get_acceptance_record(db_session, record_id)
        assert detail is not None
        assert detail.id == record_id

    @pytest.mark.asyncio
    async def test_get_acceptance_record_not_found(self, db_session: AsyncSession):
        """测试查询不存在的验收记录"""
        detail = await acceptance_service.get_acceptance_record(
            db_session, uuid.uuid4()
        )
        assert detail is None


# ============================================================
# 路由端点测试
# ============================================================


class TestAcceptanceEndpoints:
    """验收路由端点测试"""

    @pytest.mark.asyncio
    async def test_evaluate_endpoint_success(
        self, client: AsyncClient, db_session: AsyncSession
    ):
        """测试触发验收端点成功"""
        employer = await _create_user(db_session, UserType.EMPLOYER, phone="13900000201")
        headers = _get_auth_headers(employer)
        contract = await _create_contract_in_db(
            db_session, employer.id, status=ContractStatus.REVIEW
        )
        await _create_deliverable_in_db(
            db_session, contract.id,
            name="源代码",
            required_format="Git 仓库",
            file_url="https://github.com/user/repo.git",
            file_hash="a1b2c3d4e5f6a1b2c3d4e5f6a1b2c3d4e5f6a1b2c3d4e5f6a1b2c3d4e5f6a1b2",
        )

        resp = await client.post(
            f"/v1/acceptance/contracts/{contract.id}/evaluate",
            headers=headers,
        )
        assert resp.status_code == 200
        body = resp.json()
        assert body["message"] == "验收评估完成"
        assert isinstance(body["data"], list)
        assert len(body["data"]) > 0

    @pytest.mark.asyncio
    async def test_evaluate_endpoint_forbidden_for_freelancer(
        self, client: AsyncClient, db_session: AsyncSession
    ):
        """测试自由职业者不能触发验收"""
        freelancer = await _create_user(
            db_session, UserType.FREELANCER, phone="13900000202", nickname="自由者"
        )
        headers = _get_auth_headers(freelancer)
        contract = await _create_contract_in_db(
            db_session, freelancer.id, status=ContractStatus.REVIEW
        )

        resp = await client.post(
            f"/v1/acceptance/contracts/{contract.id}/evaluate",
            headers=headers,
        )
        assert resp.status_code == 403

    @pytest.mark.asyncio
    async def test_evaluate_endpoint_contract_not_found(
        self, client: AsyncClient, db_session: AsyncSession
    ):
        """测试验收不存在的合约"""
        employer = await _create_user(db_session, UserType.EMPLOYER, phone="13900000203")
        headers = _get_auth_headers(employer)

        resp = await client.post(
            f"/v1/acceptance/contracts/{uuid.uuid4()}/evaluate",
            headers=headers,
        )
        assert resp.status_code == 400

    @pytest.mark.asyncio
    async def test_list_records_endpoint(
        self, client: AsyncClient, db_session: AsyncSession
    ):
        """测试验收记录列表端点"""
        employer = await _create_user(db_session, UserType.EMPLOYER, phone="13900000204")
        headers = _get_auth_headers(employer)
        contract = await _create_contract_in_db(
            db_session, employer.id, status=ContractStatus.REVIEW
        )
        await _create_deliverable_in_db(
            db_session, contract.id,
            name="源代码",
            required_format="Git 仓库",
            file_url="https://github.com/user/repo.git",
            file_hash="a1b2c3d4e5f6a1b2c3d4e5f6a1b2c3d4e5f6a1b2c3d4e5f6a1b2c3d4e5f6a1b2",
        )

        # 先触发验收
        await client.post(
            f"/v1/acceptance/contracts/{contract.id}/evaluate",
            headers=headers,
        )

        # 查询记录
        resp = await client.get(
            f"/v1/acceptance/contracts/{contract.id}/records",
            headers=headers,
        )
        assert resp.status_code == 200
        body = resp.json()
        assert isinstance(body["data"], list)
        assert len(body["data"]) > 0

    @pytest.mark.asyncio
    async def test_get_record_detail_endpoint(
        self, client: AsyncClient, db_session: AsyncSession
    ):
        """测试验收记录详情端点"""
        employer = await _create_user(db_session, UserType.EMPLOYER, phone="13900000205")
        headers = _get_auth_headers(employer)
        contract = await _create_contract_in_db(
            db_session, employer.id, status=ContractStatus.REVIEW
        )
        await _create_deliverable_in_db(
            db_session, contract.id,
            name="源代码",
            required_format="Git 仓库",
            file_url="https://github.com/user/repo.git",
            file_hash="a1b2c3d4e5f6a1b2c3d4e5f6a1b2c3d4e5f6a1b2c3d4e5f6a1b2c3d4e5f6a1b2",
        )

        # 先触发验收
        eval_resp = await client.post(
            f"/v1/acceptance/contracts/{contract.id}/evaluate",
            headers=headers,
        )
        record_id = eval_resp.json()["data"][0]["id"]

        # 查询详情
        resp = await client.get(
            f"/v1/acceptance/records/{record_id}",
            headers=headers,
        )
        assert resp.status_code == 200
        body = resp.json()
        assert body["data"]["id"] == record_id
        assert "acceptance_report" in body["data"]

    @pytest.mark.asyncio
    async def test_get_record_detail_not_found(
        self, client: AsyncClient, db_session: AsyncSession
    ):
        """测试查询不存在的验收记录"""
        employer = await _create_user(db_session, UserType.EMPLOYER, phone="13900000206")
        headers = _get_auth_headers(employer)

        resp = await client.get(
            f"/v1/acceptance/records/{uuid.uuid4()}",
            headers=headers,
        )
        assert resp.status_code == 404

    @pytest.mark.asyncio
    async def test_reject_deliverable_endpoint(
        self, client: AsyncClient, db_session: AsyncSession
    ):
        """测试拒绝交付物端点"""
        employer = await _create_user(db_session, UserType.EMPLOYER, phone="13900000207")
        headers = _get_auth_headers(employer)
        contract = await _create_contract_in_db(
            db_session, employer.id, status=ContractStatus.REVIEW
        )
        deliverable = await _create_deliverable_in_db(db_session, contract.id)

        resp = await client.post(
            f"/v1/acceptance/deliverables/{deliverable.id}/reject",
            json={"rejection_reason": "代码质量不达标，缺少注释"},
            headers=headers,
        )
        assert resp.status_code == 200
        body = resp.json()
        assert body["message"] == "交付物已拒绝"

    @pytest.mark.asyncio
    async def test_reject_deliverable_forbidden_for_freelancer(
        self, client: AsyncClient, db_session: AsyncSession
    ):
        """测试自由职业者不能拒绝交付物"""
        freelancer = await _create_user(
            db_session, UserType.FREELANCER, phone="13900000208", nickname="自由者"
        )
        headers = _get_auth_headers(freelancer)

        resp = await client.post(
            f"/v1/acceptance/deliverables/{uuid.uuid4()}/reject",
            json={"rejection_reason": "测试"},
            headers=headers,
        )
        assert resp.status_code == 403

    @pytest.mark.asyncio
    async def test_resubmit_deliverable_endpoint(
        self, client: AsyncClient, db_session: AsyncSession
    ):
        """测试重提交付物端点"""
        freelancer = await _create_user(
            db_session, UserType.FREELANCER, phone="13900000209", nickname="自由者"
        )
        headers = _get_auth_headers(freelancer)
        employer = await _create_user(db_session, UserType.EMPLOYER, phone="13900000210")
        contract = await _create_contract_in_db(
            db_session, employer.id, status=ContractStatus.IN_PROGRESS
        )
        deliverable = await _create_deliverable_in_db(
            db_session, contract.id,
            acceptance_status=AcceptanceStatus.REJECTED,
            submit_version=1,
        )

        resp = await client.post(
            f"/v1/acceptance/deliverables/{deliverable.id}/resubmit",
            json={
                "file_url": "https://example.com/fixed_code.git",
                "file_hash": "d4e5f6a1b2c3d4e5f6a1b2c3d4e5f6a1b2c3d4e5f6a1b2c3d4e5f6a1b2c3d4e5",
            },
            headers=headers,
        )
        assert resp.status_code == 200
        body = resp.json()
        assert body["message"] == "交付物已重提"
        assert body["data"]["submit_version"] == 2
        assert body["data"]["acceptance_status"] == "pending"

    @pytest.mark.asyncio
    async def test_resubmit_deliverable_forbidden_for_employer(
        self, client: AsyncClient, db_session: AsyncSession
    ):
        """测试雇主不能重提交付物"""
        employer = await _create_user(db_session, UserType.EMPLOYER, phone="13900000211")
        headers = _get_auth_headers(employer)

        resp = await client.post(
            f"/v1/acceptance/deliverables/{uuid.uuid4()}/resubmit",
            json={
                "file_url": "https://example.com/file.pdf",
                "file_hash": "d4e5f6a1b2c3d4e5f6a1b2c3d4e5f6a1b2c3d4e5f6a1b2c3d4e5f6a1b2c3d4e5",
            },
            headers=headers,
        )
        assert resp.status_code == 403

    @pytest.mark.asyncio
    async def test_evaluate_all_approved_completes_contract(
        self, client: AsyncClient, db_session: AsyncSession
    ):
        """测试全部通过时合约自动完成"""
        employer = await _create_user(db_session, UserType.EMPLOYER, phone="13900000212")
        headers = _get_auth_headers(employer)
        contract = await _create_contract_in_db(
            db_session, employer.id, status=ContractStatus.REVIEW
        )
        # 创建格式匹配的交付物
        await _create_deliverable_in_db(
            db_session, contract.id,
            name="源代码",
            required_format="Git 仓库",
            file_url="https://github.com/user/repo.git",
            file_hash="a1b2c3d4e5f6a1b2c3d4e5f6a1b2c3d4e5f6a1b2c3d4e5f6a1b2c3d4e5f6a1b2",
        )

        resp = await client.post(
            f"/v1/acceptance/contracts/{contract.id}/evaluate",
            headers=headers,
        )
        assert resp.status_code == 200

        # 验证合约状态已变为 completed
        from app.modules.contract import service as contract_service
        updated_contract = await contract_service.get_contract(db_session, contract.id)
        assert updated_contract.status == ContractStatus.COMPLETED

    @pytest.mark.asyncio
    async def test_resubmit_max_exceeded_needs_manual_review(
        self, client: AsyncClient, db_session: AsyncSession
    ):
        """测试超过最大修改次数标记人工审核"""
        freelancer = await _create_user(
            db_session, UserType.FREELANCER, phone="13900000213", nickname="自由者"
        )
        headers = _get_auth_headers(freelancer)
        employer = await _create_user(db_session, UserType.EMPLOYER, phone="13900000214")
        contract = await _create_contract_in_db(
            db_session, employer.id, status=ContractStatus.IN_PROGRESS
        )
        deliverable = await _create_deliverable_in_db(
            db_session, contract.id,
            acceptance_status=AcceptanceStatus.REJECTED,
            submit_version=acceptance_service.MAX_RESUBMIT,
        )

        resp = await client.post(
            f"/v1/acceptance/deliverables/{deliverable.id}/resubmit",
            json={
                "file_url": "https://example.com/final_fix.git",
                "file_hash": "e5f6a1b2c3d4e5f6a1b2c3d4e5f6a1b2c3d4e5f6a1b2c3d4e5f6a1b2c3d4e5f6",
            },
            headers=headers,
        )
        assert resp.status_code == 200
        body = resp.json()
        assert body["data"]["submit_version"] == acceptance_service.MAX_RESUBMIT + 1
