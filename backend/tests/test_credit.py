"""
信用评分模块完整单元测试
覆盖：
- 雇主信用分计算
- 自由职业者信用分计算
- 冷启动策略（新用户默认 700 分）
- 信用分更新
- 信用历史记录
- 路由端点测试（GET /score, GET /history, POST /refresh, GET /users/{id}/score）
- 权限校验
"""

from __future__ import annotations

import uuid
from decimal import Decimal
from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock

import pytest
import pytest_asyncio
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.security import hash_password, create_access_token
from app.models.acceptance import AcceptanceRecord, AcceptanceResult
from app.models.contract import Contract, ContractStatus, TaskType
from app.models.transaction import Transaction, TransactionType, TransactionStatus
from app.models.user import User, UserStatus, UserType
from app.modules.credit import service as credit_service


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
        credit_score=600,
        credit_detail={},
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


async def _create_contract(
    db: AsyncSession,
    employer_id: uuid.UUID,
    freelancer_id: uuid.UUID = None,
    status: ContractStatus = ContractStatus.DRAFT,
    deadline: datetime = None,
) -> Contract:
    """创建测试合约"""
    contract = Contract(
        contract_no=f"OW-TEST-{uuid.uuid4().hex[:8]}",
        employer_id=employer_id,
        freelancer_id=freelancer_id,
        title="测试合约",
        task_type=TaskType.DEVELOPMENT,
        base_amount=Decimal("1000.00"),
        bonus_amount=Decimal("0.00"),
        status=status,
        deadline=deadline,
    )
    db.add(contract)
    await db.commit()
    await db.refresh(contract)
    return contract


async def _create_acceptance(
    db: AsyncSession,
    contract_id: uuid.UUID,
    result: AcceptanceResult = AcceptanceResult.APPROVED,
    submit_version: int = 1,
    settlement_triggered: bool = False,
) -> AcceptanceRecord:
    """创建验收记录"""
    record = AcceptanceRecord(
        contract_id=contract_id,
        submit_version=submit_version,
        acceptance_report={"score": 85},
        result=result,
        settlement_triggered=settlement_triggered,
    )
    db.add(record)
    await db.commit()
    await db.refresh(record)
    return record


async def _create_transaction(
    db: AsyncSession,
    from_user_id: uuid.UUID,
    to_user_id: uuid.UUID = None,
    transaction_type: TransactionType = TransactionType.PAYMENT,
    contract_id: uuid.UUID = None,
) -> Transaction:
    """创建交易记录"""
    tx = Transaction(
        contract_id=contract_id or uuid.uuid4(),
        transaction_type=transaction_type,
        amount=Decimal("100.00"),
        from_user_id=from_user_id,
        to_user_id=to_user_id,
        status=TransactionStatus.COMPLETED,
    )
    db.add(tx)
    await db.commit()
    await db.refresh(tx)
    return tx


# ============================================================
# 雇主信用分计算测试
# ============================================================


@pytest.mark.asyncio
async def test_employer_score_cold_start(db_session: AsyncSession):
    """新雇主（无合约）应返回冷启动默认分数 700"""
    employer = await _create_user(db_session, UserType.EMPLOYER, phone="13800000001")

    score = await credit_service.calculate_employer_score(db_session, employer.id)
    assert score == credit_service.COLD_START_SCORE


@pytest.mark.asyncio
async def test_employer_score_with_contracts(db_session: AsyncSession):
    """雇主有合约时应计算真实分数"""
    employer = await _create_user(db_session, UserType.EMPLOYER, phone="13800000001")
    freelancer = await _create_user(
        db_session, UserType.FREELANCER, phone="13800000002", email="fl@test.com"
    )

    # 创建 6 个已完成合约（超过冷启动阈值）
    for i in range(6):
        c = await _create_contract(
            db_session, employer.id, freelancer.id, ContractStatus.COMPLETED
        )
        # 创建验收通过且已结算的记录
        await _create_acceptance(
            db_session, c.id, AcceptanceResult.APPROVED, settlement_triggered=True
        )

    score = await credit_service.calculate_employer_score(db_session, employer.id)
    # 全部完成 + 全部按时结算 + 无退款 = 高分
    assert score >= 900
    assert score <= 1000


@pytest.mark.asyncio
async def test_employer_score_partial_completion(db_session: AsyncSession):
    """雇主部分完成合约时分数应降低"""
    employer = await _create_user(db_session, UserType.EMPLOYER, phone="13800000001")

    # 创建 6 个合约，只有 3 个完成
    for i in range(3):
        await _create_contract(
            db_session, employer.id, status=ContractStatus.COMPLETED
        )
    for i in range(3):
        await _create_contract(
            db_session, employer.id, status=ContractStatus.DRAFT
        )

    score = await credit_service.calculate_employer_score(db_session, employer.id)
    # 完成率 50% + 结算效率 100% + 拒付扣分 100% = weighted 80, final 600+80*4=920
    # 但低于全部完成的情况（完成率100%时 = 1000）
    assert score < 1000
    assert score >= 600


@pytest.mark.asyncio
async def test_employer_score_with_refunds(db_session: AsyncSession):
    """雇主有退款时应扣分"""
    employer = await _create_user(db_session, UserType.EMPLOYER, phone="13800000001")

    # 创建 6 个合约
    contracts = []
    for i in range(6):
        c = await _create_contract(
            db_session, employer.id, status=ContractStatus.COMPLETED
        )
        contracts.append(c)

    # 添加退款记录
    for c in contracts[:3]:
        await _create_transaction(
            db_session,
            employer.id,
            transaction_type=TransactionType.REFUND,
            contract_id=c.id,
        )

    score = await credit_service.calculate_employer_score(db_session, employer.id)
    # 有退款，分数应低于无退款情况
    assert score < 1000


# ============================================================
# 自由职业者信用分计算测试
# ============================================================


@pytest.mark.asyncio
async def test_freelancer_score_cold_start(db_session: AsyncSession):
    """新自由职业者（无合约）应返回冷启动默认分数 700"""
    freelancer = await _create_user(
        db_session, UserType.FREELANCER, phone="13800000002", email="fl@test.com"
    )

    score = await credit_service.calculate_freelancer_score(db_session, freelancer.id)
    assert score == credit_service.COLD_START_SCORE


@pytest.mark.asyncio
async def test_freelancer_score_with_contracts(db_session: AsyncSession):
    """自由职业者有合约时应计算真实分数"""
    employer = await _create_user(db_session, UserType.EMPLOYER, phone="13800000001")
    freelancer = await _create_user(
        db_session, UserType.FREELANCER, phone="13800000002", email="fl@test.com"
    )

    # 创建 6 个已完成合约，全部首次通过验收
    for i in range(6):
        c = await _create_contract(
            db_session,
            employer.id,
            freelancer.id,
            ContractStatus.COMPLETED,
            deadline=datetime(2099, 12, 31, tzinfo=timezone.utc),
        )
        await _create_acceptance(
            db_session, c.id, AcceptanceResult.APPROVED, submit_version=1
        )

    score = await credit_service.calculate_freelancer_score(db_session, freelancer.id)
    # 全部完成 + 全部首次通过 + 全部按时 = 高分
    assert score >= 900
    assert score <= 1000


@pytest.mark.asyncio
async def test_freelancer_score_with_rejects(db_session: AsyncSession):
    """自由职业者有验收拒绝时分数应降低"""
    employer = await _create_user(db_session, UserType.EMPLOYER, phone="13800000001")
    freelancer = await _create_user(
        db_session, UserType.FREELANCER, phone="13800000002", email="fl@test.com"
    )

    # 创建 6 个合约
    for i in range(6):
        c = await _create_contract(
            db_session,
            employer.id,
            freelancer.id,
            ContractStatus.COMPLETED,
            deadline=datetime(2099, 12, 31, tzinfo=timezone.utc),
        )
        # 第一次提交被拒
        await _create_acceptance(
            db_session, c.id, AcceptanceResult.REJECTED, submit_version=1
        )
        # 第二次提交通过
        await _create_acceptance(
            db_session, c.id, AcceptanceResult.APPROVED, submit_version=2
        )

    score = await credit_service.calculate_freelancer_score(db_session, freelancer.id)
    # 首次通过率为 0，分数会较低
    assert score < 900


# ============================================================
# 冷启动策略测试
# ============================================================


@pytest.mark.asyncio
async def test_cold_start_strategy_employer(db_session: AsyncSession):
    """新雇主（<5个任务）信用分更新后应为 700"""
    employer = await _create_user(db_session, UserType.EMPLOYER, phone="13800000001")

    # 创建 2 个合约（少于阈值）
    for i in range(2):
        await _create_contract(
            db_session, employer.id, status=ContractStatus.COMPLETED
        )

    updated_user = await credit_service.update_credit_score(db_session, employer.id)
    assert updated_user.credit_score == credit_service.COLD_START_SCORE

    # 检查历史记录
    history = updated_user.credit_detail.get("history", [])
    assert len(history) == 1
    assert "新用户" in history[0]["reason"]


@pytest.mark.asyncio
async def test_cold_start_strategy_freelancer(db_session: AsyncSession):
    """新自由职业者（<5个任务）信用分更新后应为 700"""
    employer = await _create_user(db_session, UserType.EMPLOYER, phone="13800000001")
    freelancer = await _create_user(
        db_session, UserType.FREELANCER, phone="13800000002", email="fl@test.com"
    )

    # 创建 3 个合约（少于阈值）
    for i in range(3):
        await _create_contract(
            db_session,
            employer.id,
            freelancer.id,
            ContractStatus.COMPLETED,
        )

    updated_user = await credit_service.update_credit_score(db_session, freelancer.id)
    assert updated_user.credit_score == credit_service.COLD_START_SCORE


@pytest.mark.asyncio
async def test_cold_start_graduation(db_session: AsyncSession):
    """完成 5 个任务后应从冷启动切换到真实分数"""
    employer = await _create_user(db_session, UserType.EMPLOYER, phone="13800000001")

    # 创建 5 个合约（达到阈值）
    for i in range(5):
        await _create_contract(
            db_session, employer.id, status=ContractStatus.COMPLETED
        )

    updated_user = await credit_service.update_credit_score(db_session, employer.id)
    # 达到阈值后使用真实计算，全部完成应得高分
    assert updated_user.credit_score >= 700
    history = updated_user.credit_detail.get("history", [])
    assert len(history) == 1
    assert "已计算" in history[0]["reason"]


# ============================================================
# 信用分更新测试
# ============================================================


@pytest.mark.asyncio
async def test_update_credit_score(db_session: AsyncSession):
    """信用分更新应正确修改用户记录"""
    employer = await _create_user(db_session, UserType.EMPLOYER, phone="13800000001")

    updated_user = await credit_service.update_credit_score(db_session, employer.id)
    assert updated_user.credit_score > 0
    assert updated_user.credit_detail is not None
    assert "history" in updated_user.credit_detail


@pytest.mark.asyncio
async def test_update_credit_score_nonexistent_user(db_session: AsyncSession):
    """更新不存在的用户应抛出 ValueError"""
    fake_id = uuid.uuid4()
    with pytest.raises(ValueError, match="用户不存在"):
        await credit_service.update_credit_score(db_session, fake_id)


@pytest.mark.asyncio
async def test_update_credit_score_history_limit(db_session: AsyncSession):
    """信用历史记录应限制在 50 条以内"""
    employer = await _create_user(db_session, UserType.EMPLOYER, phone="13800000001")

    # 模拟多次更新，每次过期旧对象以确保读取 DB 最新状态
    for i in range(55):
        # 过期 employer 对象的 credit_detail，使其下次访问时从 DB 重新加载
        db_session.expire(employer, ["credit_detail", "credit_score", "updated_at"])
        await credit_service.update_credit_score(db_session, employer.id)

    # 最终过期并验证
    db_session.expire(employer)
    await db_session.refresh(employer)
    history = employer.credit_detail.get("history", [])
    assert len(history) == 50


# ============================================================
# 信用历史查询测试
# ============================================================


@pytest.mark.asyncio
async def test_get_credit_history(db_session: AsyncSession):
    """获取信用历史应返回历史记录"""
    employer = await _create_user(db_session, UserType.EMPLOYER, phone="13800000001")

    # 先更新一次生成历史
    await credit_service.update_credit_score(db_session, employer.id)

    history_data = await credit_service.get_credit_history(db_session, employer.id)
    assert history_data["user_id"] == employer.id
    assert "history" in history_data
    assert len(history_data["history"]) >= 1


@pytest.mark.asyncio
async def test_get_credit_history_empty(db_session: AsyncSession):
    """未更新过的用户历史记录应为空"""
    employer = await _create_user(db_session, UserType.EMPLOYER, phone="13800000001")

    history_data = await credit_service.get_credit_history(db_session, employer.id)
    assert history_data["history"] == []


@pytest.mark.asyncio
async def test_get_credit_history_nonexistent_user(db_session: AsyncSession):
    """查询不存在的用户应抛出 ValueError"""
    fake_id = uuid.uuid4()
    with pytest.raises(ValueError, match="用户不存在"):
        await credit_service.get_credit_history(db_session, fake_id)


# ============================================================
# 信用等级映射测试
# ============================================================


def test_credit_level_mapping():
    """信用等级映射应正确"""
    assert credit_service._get_credit_level(950) == "优秀"
    assert credit_service._get_credit_level(900) == "优秀"
    assert credit_service._get_credit_level(850) == "良好"
    assert credit_service._get_credit_level(800) == "良好"
    assert credit_service._get_credit_level(750) == "中等"
    assert credit_service._get_credit_level(700) == "中等"
    assert credit_service._get_credit_level(650) == "一般"
    assert credit_service._get_credit_level(600) == "一般"
    assert credit_service._get_credit_level(500) == "较差"
    assert credit_service._get_credit_level(300) == "极差"


# ============================================================
# 路由端点测试
# ============================================================


@pytest.mark.asyncio
async def test_get_my_credit_score(db_session: AsyncSession, client: AsyncClient):
    """GET /v1/credit/score 应返回当前用户信用分"""
    employer = await _create_user(db_session, UserType.EMPLOYER, phone="13800000001")
    headers = _get_auth_headers(employer)

    resp = await client.get("/v1/credit/score", headers=headers)
    assert resp.status_code == 200
    body = resp.json()
    assert body["code"] == 200
    assert body["data"]["credit_score"] == 600
    assert body["data"]["user_id"] == str(employer.id)


@pytest.mark.asyncio
async def test_get_my_credit_history(db_session: AsyncSession, client: AsyncClient):
    """GET /v1/credit/history 应返回历史记录"""
    # CREDIT_HISTORY 是管理员权限，使用管理员用户
    admin = await _create_user(db_session, UserType.ADMIN, phone="13800000001")
    # 先刷新一次生成历史
    await credit_service.update_credit_score(db_session, admin.id)

    headers = _get_auth_headers(admin)
    resp = await client.get("/v1/credit/history", headers=headers)
    assert resp.status_code == 200
    body = resp.json()
    assert body["code"] == 200
    assert isinstance(body["data"]["history"], list)


@pytest.mark.asyncio
async def test_refresh_credit_score(db_session: AsyncSession, client: AsyncClient):
    """POST /v1/credit/refresh 应刷新信用分"""
    employer = await _create_user(db_session, UserType.EMPLOYER, phone="13800000001")
    headers = _get_auth_headers(employer)

    resp = await client.post("/v1/credit/refresh", headers=headers)
    assert resp.status_code == 200
    body = resp.json()
    assert body["code"] == 200
    assert "credit_score" in body["data"]
    assert body["message"] == "信用分已刷新"


@pytest.mark.asyncio
async def test_get_user_credit_score(db_session: AsyncSession, client: AsyncClient):
    """GET /v1/credit/users/{user_id}/score 应返回指定用户信用分"""
    employer = await _create_user(db_session, UserType.EMPLOYER, phone="13800000001")
    viewer = await _create_user(
        db_session, UserType.FREELANCER, phone="13800000002", email="viewer@test.com"
    )
    headers = _get_auth_headers(viewer)

    resp = await client.get(
        f"/v1/credit/users/{employer.id}/score", headers=headers
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["code"] == 200
    assert body["data"]["user_id"] == str(employer.id)


@pytest.mark.asyncio
async def test_get_user_credit_score_not_found(
    db_session: AsyncSession, client: AsyncClient
):
    """查询不存在的用户应返回 404"""
    viewer = await _create_user(
        db_session, UserType.FREELANCER, phone="13800000002", email="viewer@test.com"
    )
    headers = _get_auth_headers(viewer)

    fake_id = uuid.uuid4()
    resp = await client.get(
        f"/v1/credit/users/{fake_id}/score", headers=headers
    )
    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_endpoints_require_auth(client: AsyncClient):
    """未认证请求应返回 401/403"""
    resp = await client.get("/v1/credit/score")
    assert resp.status_code in (401, 403)

    resp = await client.get("/v1/credit/history")
    assert resp.status_code in (401, 403)

    resp = await client.post("/v1/credit/refresh")
    assert resp.status_code in (401, 403)
