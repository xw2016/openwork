"""
资金托管与结算模块单元测试
覆盖：
- 2.16 资金托管流程（create_escrow）
- 2.17 自动结算（release_escrow）
- 2.18 退款与终止（refund_escrow）
- 交易记录查询（list_transactions）
- 边界条件与错误路径
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
from app.models.transaction import Transaction, TransactionStatus, TransactionType
from app.models.user import User, UserStatus, UserType
from app.modules.payment import service as payment_service


# ============================================================
# 辅助函数
# ============================================================


async def _create_user(
    db: AsyncSession,
    user_type: UserType = UserType.EMPLOYER,
    phone: str = "13800000001",
    nickname: str = "测试用户",
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


async def _create_contract_in_db(
    db: AsyncSession,
    employer_id: uuid.UUID,
    status: ContractStatus = ContractStatus.DRAFT,
    freelancer_id: uuid.UUID = None,
    base_amount: Decimal = Decimal("5000.00"),
    bonus_amount: Decimal = Decimal("0.00"),
    commission_rate: Decimal = Decimal("0.05"),
) -> Contract:
    """直接在数据库中创建合约"""
    contract = Contract(
        contract_no=f"OW-TEST-{uuid.uuid4().hex[:8]}",
        employer_id=employer_id,
        freelancer_id=freelancer_id,
        title="测试资金托管合约",
        task_type=TaskType.DEVELOPMENT,
        intent_blueprint={},
        deliverables=[],
        base_amount=base_amount,
        bonus_amount=bonus_amount,
        commission_rate=commission_rate,
        status=status,
    )
    db.add(contract)
    await db.commit()
    await db.refresh(contract)
    return contract


async def _create_escrow_in_db(
    db: AsyncSession,
    contract_id: uuid.UUID,
    employer_id: uuid.UUID,
    amount: Decimal = Decimal("5000.00"),
    status: TransactionStatus = TransactionStatus.PENDING,
) -> Transaction:
    """直接在数据库中创建 escrow 交易"""
    escrow = Transaction(
        contract_id=contract_id,
        transaction_type=TransactionType.ESCROW,
        amount=amount,
        from_user_id=employer_id,
        to_user_id=None,
        commission=Decimal("0.00"),
        status=status,
    )
    db.add(escrow)
    await db.commit()
    await db.refresh(escrow)
    return escrow


# ============================================================
# 2.16 资金托管流程测试（Service 层）
# ============================================================


class TestCreateEscrow:
    """资金托管创建测试"""

    @pytest.mark.asyncio
    async def test_create_escrow_success(self, db_session: AsyncSession):
        """测试雇主成功创建资金托管"""
        employer = await _create_user(db_session, UserType.EMPLOYER, phone="13810000001")
        contract = await _create_contract_in_db(
            db_session, employer.id, status=ContractStatus.IN_PROGRESS
        )

        escrow = await payment_service.create_escrow(
            db_session, contract.id, employer.id, Decimal("5000.00")
        )

        assert escrow.transaction_type == TransactionType.ESCROW
        assert escrow.amount == Decimal("5000.00")
        assert escrow.from_user_id == employer.id
        assert escrow.to_user_id is None
        assert escrow.status == TransactionStatus.PENDING
        assert escrow.commission == Decimal("0.00")

    @pytest.mark.asyncio
    async def test_create_escrow_with_bonus(self, db_session: AsyncSession):
        """测试托管金额包含奖金"""
        employer = await _create_user(db_session, UserType.EMPLOYER, phone="13810000002")
        contract = await _create_contract_in_db(
            db_session,
            employer.id,
            status=ContractStatus.IN_PROGRESS,
            base_amount=Decimal("5000.00"),
            bonus_amount=Decimal("1000.00"),
        )

        escrow = await payment_service.create_escrow(
            db_session, contract.id, employer.id, Decimal("6000.00")
        )

        assert escrow.amount == Decimal("6000.00")

    @pytest.mark.asyncio
    async def test_create_escrow_contract_not_found(self, db_session: AsyncSession):
        """测试合约不存在"""
        employer = await _create_user(db_session, UserType.EMPLOYER, phone="13810000003")
        fake_id = uuid.uuid4()

        with pytest.raises(ValueError, match="合约不存在"):
            await payment_service.create_escrow(
                db_session, fake_id, employer.id, Decimal("5000.00")
            )

    @pytest.mark.asyncio
    async def test_create_escrow_not_employer(self, db_session: AsyncSession):
        """测试非雇主创建托管失败"""
        employer = await _create_user(db_session, UserType.EMPLOYER, phone="13810000004")
        other_user = await _create_user(
            db_session, UserType.FREELANCER, phone="13810000005", nickname="非雇主"
        )
        contract = await _create_contract_in_db(
            db_session, employer.id, status=ContractStatus.IN_PROGRESS
        )

        with pytest.raises(ValueError, match="只有合约的雇主"):
            await payment_service.create_escrow(
                db_session, contract.id, other_user.id, Decimal("5000.00")
            )

    @pytest.mark.asyncio
    async def test_create_escrow_amount_mismatch(self, db_session: AsyncSession):
        """测试金额不匹配"""
        employer = await _create_user(db_session, UserType.EMPLOYER, phone="13810000006")
        contract = await _create_contract_in_db(
            db_session, employer.id, status=ContractStatus.IN_PROGRESS
        )

        with pytest.raises(ValueError, match="托管金额不匹配"):
            await payment_service.create_escrow(
                db_session, contract.id, employer.id, Decimal("9999.00")
            )


# ============================================================
# 2.17 自动结算测试（Service 层）
# ============================================================


class TestReleaseEscrow:
    """资金释放测试"""

    @pytest.mark.asyncio
    async def test_release_escrow_success(self, db_session: AsyncSession):
        """测试验收通过后成功释放资金"""
        employer = await _create_user(db_session, UserType.EMPLOYER, phone="13820000001")
        freelancer = await _create_user(
            db_session, UserType.FREELANCER, phone="13820000002", nickname="自由者"
        )
        contract = await _create_contract_in_db(
            db_session,
            employer.id,
            status=ContractStatus.REVIEW,
            freelancer_id=freelancer.id,
            base_amount=Decimal("10000.00"),
            bonus_amount=Decimal("2000.00"),
            commission_rate=Decimal("0.05"),
        )
        await _create_escrow_in_db(
            db_session, contract.id, employer.id, Decimal("12000.00")
        )

        payment = await payment_service.release_escrow(db_session, contract.id)

        # 验证 payment 交易
        assert payment.transaction_type == TransactionType.PAYMENT
        assert payment.amount == Decimal("12000.00")  # base + bonus
        assert payment.from_user_id == employer.id
        assert payment.to_user_id == freelancer.id
        assert payment.status == TransactionStatus.COMPLETED
        # 佣金 = 12000 * 0.05 = 600
        assert payment.commission == Decimal("600.0000")

    @pytest.mark.asyncio
    async def test_release_escrow_no_freelancer(self, db_session: AsyncSession):
        """测试合约没有自由职业者时释放失败"""
        employer = await _create_user(db_session, UserType.EMPLOYER, phone="13820000003")
        contract = await _create_contract_in_db(
            db_session, employer.id, status=ContractStatus.PENDING, freelancer_id=None
        )
        await _create_escrow_in_db(
            db_session, contract.id, employer.id, Decimal("5000.00")
        )

        with pytest.raises(ValueError, match="尚未分配自由职业者"):
            await payment_service.release_escrow(db_session, contract.id)

    @pytest.mark.asyncio
    async def test_release_escrow_no_pending_escrow(self, db_session: AsyncSession):
        """测试没有 pending 状态的 escrow 时释放失败"""
        employer = await _create_user(db_session, UserType.EMPLOYER, phone="13820000004")
        freelancer = await _create_user(
            db_session, UserType.FREELANCER, phone="13820000005", nickname="自由者"
        )
        contract = await _create_contract_in_db(
            db_session,
            employer.id,
            status=ContractStatus.REVIEW,
            freelancer_id=freelancer.id,
        )
        # 没有创建 escrow 交易

        with pytest.raises(ValueError, match="未找到有效的托管交易"):
            await payment_service.release_escrow(db_session, contract.id)

    @pytest.mark.asyncio
    async def test_release_escrow_marks_escrow_completed(self, db_session: AsyncSession):
        """测试释放后原 escrow 状态变为 completed"""
        employer = await _create_user(db_session, UserType.EMPLOYER, phone="13820000006")
        freelancer = await _create_user(
            db_session, UserType.FREELANCER, phone="13820000007", nickname="自由者"
        )
        contract = await _create_contract_in_db(
            db_session,
            employer.id,
            status=ContractStatus.REVIEW,
            freelancer_id=freelancer.id,
        )
        escrow = await _create_escrow_in_db(
            db_session, contract.id, employer.id, Decimal("5000.00")
        )

        await payment_service.release_escrow(db_session, contract.id)

        # 刷新 escrow 记录
        await db_session.refresh(escrow)
        assert escrow.status == TransactionStatus.COMPLETED

    @pytest.mark.asyncio
    async def test_release_escrow_commission_calculation(self, db_session: AsyncSession):
        """测试佣金计算准确性"""
        employer = await _create_user(db_session, UserType.EMPLOYER, phone="13820000008")
        freelancer = await _create_user(
            db_session, UserType.FREELANCER, phone="13820000009", nickname="自由者"
        )
        contract = await _create_contract_in_db(
            db_session,
            employer.id,
            status=ContractStatus.REVIEW,
            freelancer_id=freelancer.id,
            base_amount=Decimal("10000.00"),
            bonus_amount=Decimal("0.00"),
            commission_rate=Decimal("0.10"),
        )
        await _create_escrow_in_db(
            db_session, contract.id, employer.id, Decimal("10000.00")
        )

        payment = await payment_service.release_escrow(db_session, contract.id)

        # 佣金 = 10000 * 0.10 = 1000
        assert payment.commission == Decimal("1000.0000")
        assert payment.amount == Decimal("10000.00")


# ============================================================
# 2.18 退款与终止测试（Service 层）
# ============================================================


class TestRefundEscrow:
    """退款测试"""

    @pytest.mark.asyncio
    async def test_refund_escrow_success(self, db_session: AsyncSession):
        """测试退款成功"""
        employer = await _create_user(db_session, UserType.EMPLOYER, phone="13830000001")
        contract = await _create_contract_in_db(
            db_session, employer.id, status=ContractStatus.TERMINATED
        )
        escrow = await _create_escrow_in_db(
            db_session, contract.id, employer.id, Decimal("5000.00")
        )

        refund_tx = await payment_service.refund_escrow(
            db_session, contract.id, reason="合约终止退款"
        )

        assert refund_tx.transaction_type == TransactionType.REFUND
        assert refund_tx.amount == Decimal("5000.00")
        assert refund_tx.to_user_id == employer.id
        assert refund_tx.from_user_id is None
        assert refund_tx.status == TransactionStatus.COMPLETED
        assert refund_tx.commission == Decimal("0.00")

    @pytest.mark.asyncio
    async def test_refund_escrow_cancels_original(self, db_session: AsyncSession):
        """测试退款后原 escrow 状态变为 cancelled"""
        employer = await _create_user(db_session, UserType.EMPLOYER, phone="13830000002")
        contract = await _create_contract_in_db(
            db_session, employer.id, status=ContractStatus.TERMINATED
        )
        escrow = await _create_escrow_in_db(
            db_session, contract.id, employer.id, Decimal("5000.00")
        )

        await payment_service.refund_escrow(db_session, contract.id, reason="测试")

        await db_session.refresh(escrow)
        assert escrow.status == TransactionStatus.CANCELLED

    @pytest.mark.asyncio
    async def test_refund_escrow_contract_not_found(self, db_session: AsyncSession):
        """测试合约不存在时退款失败"""
        employer = await _create_user(db_session, UserType.EMPLOYER, phone="13830000003")
        fake_id = uuid.uuid4()

        with pytest.raises(ValueError, match="合约不存在"):
            await payment_service.refund_escrow(db_session, fake_id, reason="测试")

    @pytest.mark.asyncio
    async def test_refund_escrow_no_escrow_transaction(self, db_session: AsyncSession):
        """测试没有 escrow 交易时退款失败"""
        employer = await _create_user(db_session, UserType.EMPLOYER, phone="13830000004")
        contract = await _create_contract_in_db(
            db_session, employer.id, status=ContractStatus.TERMINATED
        )
        # 不创建 escrow

        with pytest.raises(ValueError, match="未找到有效的托管交易"):
            await payment_service.refund_escrow(db_session, contract.id, reason="测试")

    @pytest.mark.asyncio
    async def test_refund_completed_escrow(self, db_session: AsyncSession):
        """测试已完成的 escrow 也可以退款"""
        employer = await _create_user(db_session, UserType.EMPLOYER, phone="13830000005")
        contract = await _create_contract_in_db(
            db_session, employer.id, status=ContractStatus.TERMINATED
        )
        escrow = await _create_escrow_in_db(
            db_session,
            contract.id,
            employer.id,
            Decimal("5000.00"),
            status=TransactionStatus.COMPLETED,
        )

        refund_tx = await payment_service.refund_escrow(
            db_session, contract.id, reason="已完成托管退款"
        )

        assert refund_tx.transaction_type == TransactionType.REFUND
        assert refund_tx.amount == Decimal("5000.00")

    @pytest.mark.asyncio
    async def test_refund_failed_escrow_fails(self, db_session: AsyncSession):
        """测试 failed 状态的 escrow 不能退款"""
        employer = await _create_user(db_session, UserType.EMPLOYER, phone="13830000006")
        contract = await _create_contract_in_db(
            db_session, employer.id, status=ContractStatus.TERMINATED
        )
        await _create_escrow_in_db(
            db_session,
            contract.id,
            employer.id,
            Decimal("5000.00"),
            status=TransactionStatus.FAILED,
        )

        with pytest.raises(ValueError, match="未找到有效的托管交易"):
            await payment_service.refund_escrow(db_session, contract.id, reason="测试")


# ============================================================
# 交易记录查询测试
# ============================================================


class TestListTransactions:
    """交易记录查询测试"""

    @pytest.mark.asyncio
    async def test_list_transactions_empty(self, db_session: AsyncSession):
        """测试查询空交易记录"""
        contract_id = uuid.uuid4()
        result = await payment_service.list_transactions(db_session, contract_id)

        assert result["total"] == 0
        assert result["items"] == []

    @pytest.mark.asyncio
    async def test_list_transactions_with_data(self, db_session: AsyncSession):
        """测试查询有数据的交易记录"""
        employer = await _create_user(db_session, UserType.EMPLOYER, phone="13840000001")
        contract = await _create_contract_in_db(
            db_session, employer.id, status=ContractStatus.IN_PROGRESS
        )
        # 创建 escrow 交易
        await _create_escrow_in_db(
            db_session, contract.id, employer.id, Decimal("5000.00")
        )

        result = await payment_service.list_transactions(db_session, contract.id)

        assert result["total"] == 1
        assert len(result["items"]) == 1
        assert result["items"][0].transaction_type == TransactionType.ESCROW

    @pytest.mark.asyncio
    async def test_list_transactions_pagination(self, db_session: AsyncSession):
        """测试分页查询"""
        employer = await _create_user(db_session, UserType.EMPLOYER, phone="13840000002")
        contract = await _create_contract_in_db(
            db_session, employer.id, status=ContractStatus.IN_PROGRESS
        )
        # 创建多条交易记录
        for i in range(5):
            tx = Transaction(
                contract_id=contract.id,
                transaction_type=TransactionType.PAYMENT,
                amount=Decimal("100.00"),
                from_user_id=employer.id,
                commission=Decimal("0.00"),
                status=TransactionStatus.COMPLETED,
            )
            db_session.add(tx)
        await db_session.commit()

        # 查询第一页
        result = await payment_service.list_transactions(
            db_session, contract.id, page=1, size=3
        )
        assert result["total"] == 5
        assert len(result["items"]) == 3
        assert result["total_pages"] == 2

        # 查询第二页
        result = await payment_service.list_transactions(
            db_session, contract.id, page=2, size=3
        )
        assert len(result["items"]) == 2


# ============================================================
# API 端点集成测试
# ============================================================


class TestPaymentAPI:
    """资金结算 API 端点集成测试"""

    @pytest.mark.asyncio
    async def test_escrow_api_success(
        self, client: AsyncClient, db_session: AsyncSession
    ):
        """测试通过 API 创建资金托管"""
        employer = await _create_user(db_session, UserType.EMPLOYER, phone="13850000001")
        headers = _get_auth_headers(employer)
        contract = await _create_contract_in_db(
            db_session, employer.id, status=ContractStatus.IN_PROGRESS
        )

        resp = await client.post(
            "/v1/payment/escrow",
            json={
                "contract_id": str(contract.id),
                "amount": "5000.00",
            },
            headers=headers,
        )
        assert resp.status_code == 201
        body = resp.json()
        assert body["code"] == 201
        assert body["message"] == "资金托管创建成功"
        assert body["data"]["transaction_type"] == "escrow"
        assert body["data"]["status"] == "pending"

    @pytest.mark.asyncio
    async def test_escrow_api_amount_mismatch(
        self, client: AsyncClient, db_session: AsyncSession
    ):
        """测试 API 托管金额不匹配"""
        employer = await _create_user(db_session, UserType.EMPLOYER, phone="13850000002")
        headers = _get_auth_headers(employer)
        contract = await _create_contract_in_db(
            db_session, employer.id, status=ContractStatus.IN_PROGRESS
        )

        resp = await client.post(
            "/v1/payment/escrow",
            json={
                "contract_id": str(contract.id),
                "amount": "9999.00",
            },
            headers=headers,
        )
        assert resp.status_code == 400

    @pytest.mark.asyncio
    async def test_release_api_success(
        self, client: AsyncClient, db_session: AsyncSession
    ):
        """测试通过 API 释放资金"""
        employer = await _create_user(db_session, UserType.EMPLOYER, phone="13850000003")
        freelancer = await _create_user(
            db_session, UserType.FREELANCER, phone="13850000004", nickname="自由者"
        )
        headers = _get_auth_headers(employer)
        contract = await _create_contract_in_db(
            db_session,
            employer.id,
            status=ContractStatus.REVIEW,
            freelancer_id=freelancer.id,
        )
        await _create_escrow_in_db(
            db_session, contract.id, employer.id, Decimal("5000.00")
        )

        resp = await client.post(
            f"/v1/payment/contracts/{contract.id}/release",
            headers=headers,
        )
        assert resp.status_code == 200
        body = resp.json()
        assert body["message"] == "资金释放成功"
        assert body["data"]["transaction_type"] == "payment"
        assert body["data"]["status"] == "completed"

    @pytest.mark.asyncio
    async def test_refund_api_success(
        self, client: AsyncClient, db_session: AsyncSession
    ):
        """测试通过 API 退款"""
        employer = await _create_user(db_session, UserType.EMPLOYER, phone="13850000005")
        headers = _get_auth_headers(employer)
        contract = await _create_contract_in_db(
            db_session, employer.id, status=ContractStatus.TERMINATED
        )
        await _create_escrow_in_db(
            db_session, contract.id, employer.id, Decimal("5000.00")
        )

        resp = await client.post(
            f"/v1/payment/contracts/{contract.id}/refund",
            json={"reason": "合约终止退款"},
            headers=headers,
        )
        assert resp.status_code == 200
        body = resp.json()
        assert body["message"] == "退款成功"
        assert body["data"]["transaction_type"] == "refund"

    @pytest.mark.asyncio
    async def test_list_transactions_api_success(
        self, client: AsyncClient, db_session: AsyncSession
    ):
        """测试通过 API 查询交易记录"""
        employer = await _create_user(db_session, UserType.EMPLOYER, phone="13850000006")
        headers = _get_auth_headers(employer)
        contract = await _create_contract_in_db(
            db_session, employer.id, status=ContractStatus.IN_PROGRESS
        )
        await _create_escrow_in_db(
            db_session, contract.id, employer.id, Decimal("5000.00")
        )

        resp = await client.get(
            f"/v1/payment/contracts/{contract.id}/transactions",
            headers=headers,
        )
        assert resp.status_code == 200
        body = resp.json()
        assert body["data"]["total"] == 1
        assert len(body["data"]["items"]) == 1

    @pytest.mark.asyncio
    async def test_escrow_api_unauthorized(
        self, client: AsyncClient, db_session: AsyncSession
    ):
        """测试未认证访问"""
        resp = await client.post(
            "/v1/payment/escrow",
            json={
                "contract_id": str(uuid.uuid4()),
                "amount": "5000.00",
            },
        )
        assert resp.status_code == 401  # 无 Bearer token

    @pytest.mark.asyncio
    async def test_release_api_no_escrow(
        self, client: AsyncClient, db_session: AsyncSession
    ):
        """测试释放资金时无 escrow 交易"""
        employer = await _create_user(db_session, UserType.EMPLOYER, phone="13850000007")
        freelancer = await _create_user(
            db_session, UserType.FREELANCER, phone="13850000008", nickname="自由者"
        )
        headers = _get_auth_headers(employer)
        contract = await _create_contract_in_db(
            db_session,
            employer.id,
            status=ContractStatus.REVIEW,
            freelancer_id=freelancer.id,
        )

        resp = await client.post(
            f"/v1/payment/contracts/{contract.id}/release",
            headers=headers,
        )
        assert resp.status_code == 400
