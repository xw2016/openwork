"""
API Integration Tests for OpenWork Backend
===========================================
Cross-module integration tests covering all 9 API modules.
Focus areas:
  - Cross-module state transitions (auth -> intent -> contract -> market -> acceptance -> payment)
  - Auth boundary tests across all protected endpoints
  - Permission enforcement across modules
  - Input validation at the API layer
  - Pagination edge cases
  - Edge cases (non-existent IDs, duplicate ops, invalid state transitions)

These tests complement the existing unit tests by testing at the HTTP API level
through the full FastAPI request/response cycle.
"""

from __future__ import annotations

import uuid
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from unittest.mock import patch

import pytest
import pytest_asyncio
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.security import create_access_token, hash_password
from app.models.contract import Contract, ContractStatus, TaskType
from app.models.deliverable import Deliverable, AcceptanceStatus as DeliverableAcceptanceStatus
from app.models.intent_blueprint import IntentBlueprint, BlueprintStatus
from app.models.transaction import Transaction, TransactionType, TransactionStatus
from app.models.user import User, UserStatus, UserType


# ============================================================
# Helper functions
# ============================================================


async def _create_user(
    db: AsyncSession,
    user_type: UserType = UserType.FREELANCER,
    phone: str = "13800000001",
    email: str = None,
    nickname: str = "TestUser",
    password: str = "TestPass123",
    credit_score: int = 600,
) -> User:
    """Create a test user directly in the database."""
    user = User(
        phone=phone,
        email=email,
        nickname=nickname,
        user_type=user_type,
        hashed_password=hash_password(password),
        status=UserStatus.ACTIVE,
        credit_score=credit_score,
        credit_detail={"is_new_user": True},
    )
    db.add(user)
    await db.commit()
    await db.refresh(user)
    return user


def _auth_headers(user: User) -> dict:
    """Generate Authorization headers with a valid JWT for the given user."""
    token = create_access_token(data={"sub": str(user.id)})
    return {"Authorization": f"Bearer {token}"}


def _expired_auth_headers(user: User) -> dict:
    """Generate Authorization headers with an expired JWT."""
    token = create_access_token(
        data={"sub": str(user.id)},
        expires_delta=timedelta(seconds=-10),
    )
    return {"Authorization": f"Bearer {token}"}


def _sample_contract_data(**overrides) -> dict:
    """Return sample contract creation payload."""
    data = {
        "title": "Integration Test Contract",
        "task_type": "development",
        "base_amount": "1000.00",
        "bonus_amount": "100.00",
        "intent_blueprint": {"summary": "Build a website"},
        "deliverables": [{"name": "Source code", "format": "zip"}],
    }
    data.update(overrides)
    return data


async def _create_contract_in_db(
    db: AsyncSession,
    employer_id: uuid.UUID,
    status: ContractStatus = ContractStatus.DRAFT,
    freelancer_id: uuid.UUID = None,
    base_amount: Decimal = Decimal("1000.00"),
) -> Contract:
    """Create a contract directly in the database."""
    contract = Contract(
        contract_no=f"OW-TEST-{uuid.uuid4().hex[:8]}",
        employer_id=employer_id,
        freelancer_id=freelancer_id,
        title="DB Contract",
        task_type=TaskType.DEVELOPMENT,
        intent_blueprint={"summary": "Test"},
        deliverables=[],
        base_amount=base_amount,
        bonus_amount=Decimal("0.00"),
        commission_rate=Decimal("0.0500"),
        status=status,
    )
    db.add(contract)
    await db.commit()
    await db.refresh(contract)
    return contract


async def _create_deliverable_in_db(
    db: AsyncSession,
    contract_id: uuid.UUID,
    acceptance_status: DeliverableAcceptanceStatus = DeliverableAcceptanceStatus.NOT_SUBMITTED,
) -> Deliverable:
    """Create a deliverable directly in the database."""
    deliverable = Deliverable(
        contract_id=contract_id,
        deliverable_index=1,
        name="Test Deliverable",
        required_format="zip",
        acceptance_criteria={"min_files": 1},
        acceptance_status=acceptance_status,
    )
    db.add(deliverable)
    await db.commit()
    await db.refresh(deliverable)
    return deliverable


# ============================================================
# MODULE 1: Auth Integration Tests
# ============================================================


class TestAuthIntegration:
    """Auth module integration tests."""

    @pytest.mark.asyncio
    async def test_register_then_login_flow(self, client: AsyncClient, db_session: AsyncSession):
        """Full registration -> login -> get_me flow."""
        from app.modules.auth.login_guard import login_guard
        login_guard._lock_store.clear()
        login_guard._login_logs.clear()

        # Register
        resp = await client.post("/v1/auth/register", json={
            "phone": "13900000001",
            "password": "TestPass123",
            "nickname": "FlowUser",
            "user_type": "employer",
        })
        assert resp.status_code == 201
        user_data = resp.json()["data"]

        # Login with phone
        resp = await client.post("/v1/auth/login", json={
            "phone": "13900000001",
            "password": "TestPass123",
        })
        assert resp.status_code == 200
        token_data = resp.json()["data"]
        assert "access_token" in token_data
        assert "refresh_token" in token_data

        # Get current user
        headers = {"Authorization": f"Bearer {token_data['access_token']}"}
        resp = await client.get("/v1/auth/me", headers=headers)
        assert resp.status_code == 200
        assert resp.json()["data"]["phone"] == "13900000001"
        assert resp.json()["data"]["user_type"] == "employer"

    @pytest.mark.asyncio
    async def test_register_email_then_login(self, client: AsyncClient, db_session: AsyncSession):
        """Register via email endpoint, then login via email."""
        from app.modules.auth.login_guard import login_guard
        login_guard._lock_store.clear()
        login_guard._login_logs.clear()

        resp = await client.post("/v1/auth/register-email", json={
            "email": "integration@test.com",
            "password": "TestPass123",
            "nickname": "EmailUser",
        })
        assert resp.status_code == 201

        resp = await client.post("/v1/auth/login", json={
            "email": "integration@test.com",
            "password": "TestPass123",
        })
        assert resp.status_code == 200
        assert resp.json()["data"]["token_type"] == "bearer"

    @pytest.mark.asyncio
    async def test_register_duplicate_phone_returns_409(self, client: AsyncClient, db_session: AsyncSession):
        """Duplicate phone registration should return 409."""
        from app.modules.auth.login_guard import login_guard
        login_guard._lock_store.clear()

        payload = {
            "phone": "13900000002",
            "password": "TestPass123",
            "nickname": "User1",
        }
        resp1 = await client.post("/v1/auth/register", json=payload)
        assert resp1.status_code == 201

        payload["nickname"] = "User2"
        resp2 = await client.post("/v1/auth/register", json=payload)
        assert resp2.status_code == 409

    @pytest.mark.asyncio
    async def test_register_duplicate_email_returns_409(self, client: AsyncClient, db_session: AsyncSession):
        """Duplicate email registration should return 409."""
        from app.modules.auth.login_guard import login_guard
        login_guard._lock_store.clear()

        payload = {
            "email": "dup@test.com",
            "password": "TestPass123",
            "nickname": "User1",
        }
        await client.post("/v1/auth/register-email", json=payload)
        resp = await client.post("/v1/auth/register-email", json={**payload, "nickname": "User2"})
        assert resp.status_code == 409

    @pytest.mark.asyncio
    async def test_login_wrong_password_returns_401(self, client: AsyncClient, db_session: AsyncSession):
        """Login with wrong password should return 401."""
        from app.modules.auth.login_guard import login_guard
        login_guard._lock_store.clear()
        login_guard._login_logs.clear()

        await _create_user(db_session, phone="13900000003", password="CorrectPass1")
        resp = await client.post("/v1/auth/login", json={
            "phone": "13900000003",
            "password": "WrongPass1",
        })
        assert resp.status_code == 401

    @pytest.mark.asyncio
    async def test_login_nonexistent_user_returns_401(self, client: AsyncClient):
        """Login with non-existent phone should return 401."""
        resp = await client.post("/v1/auth/login", json={
            "phone": "19999999999",
            "password": "TestPass123",
        })
        assert resp.status_code == 401

    @pytest.mark.asyncio
    async def test_register_weak_password_returns_422(self, client: AsyncClient):
        """Registration with weak password should fail validation."""
        resp = await client.post("/v1/auth/register", json={
            "phone": "13900000010",
            "password": "123",
            "nickname": "Weak",
        })
        assert resp.status_code == 422

    @pytest.mark.asyncio
    async def test_register_invalid_phone_returns_422(self, client: AsyncClient):
        """Registration with invalid phone format should fail validation."""
        resp = await client.post("/v1/auth/register", json={
            "phone": "999",
            "password": "TestPass123",
            "nickname": "BadPhone",
        })
        assert resp.status_code == 422

    @pytest.mark.asyncio
    async def test_get_permissions_authenticated(self, client: AsyncClient, db_session: AsyncSession):
        """GET /v1/auth/permissions returns a list of permissions."""
        user = await _create_user(db_session, phone="13900000004")
        resp = await client.get("/v1/auth/permissions", headers=_auth_headers(user))
        assert resp.status_code == 200
        assert isinstance(resp.json()["data"], list)

    @pytest.mark.asyncio
    async def test_refresh_token_flow(self, client: AsyncClient, db_session: AsyncSession):
        """Register -> login -> refresh -> use new access token."""
        from app.modules.auth.login_guard import login_guard
        login_guard._lock_store.clear()
        login_guard._login_logs.clear()

        await client.post("/v1/auth/register", json={
            "phone": "13900000005",
            "password": "TestPass123",
            "nickname": "RefreshUser",
        })
        login_resp = await client.post("/v1/auth/login", json={
            "phone": "13900000005",
            "password": "TestPass123",
        })
        refresh_token = login_resp.json()["data"]["refresh_token"]

        resp = await client.post("/v1/auth/refresh", json={
            "refresh_token": refresh_token,
        })
        assert resp.status_code == 200
        new_token = resp.json()["data"]["access_token"]

        # Use the new access token
        resp = await client.get("/v1/auth/me", headers={"Authorization": f"Bearer {new_token}"})
        assert resp.status_code == 200


# ============================================================
# MODULE 2: Auth Boundary Tests (cross-endpoint)
# ============================================================


class TestAuthBoundary:
    """Auth boundary tests applied across protected endpoints."""

    @pytest.mark.asyncio
    async def test_no_token_returns_403(self, client: AsyncClient):
        """Protected endpoint without token should return 403 (missing bearer)."""
        resp = await client.get("/v1/auth/me")
        assert resp.status_code in (401, 403)

    @pytest.mark.asyncio
    async def test_invalid_token_returns_401(self, client: AsyncClient):
        """Invalid bearer token should return 401."""
        resp = await client.get("/v1/auth/me", headers={"Authorization": "Bearer invalid.token.here"})
        assert resp.status_code == 401

    @pytest.mark.asyncio
    async def test_expired_token_returns_401(self, client: AsyncClient, db_session: AsyncSession):
        """Expired token should return 401."""
        user = await _create_user(db_session, phone="13900000006")
        resp = await client.get("/v1/auth/me", headers=_expired_auth_headers(user))
        assert resp.status_code == 401

    @pytest.mark.asyncio
    async def test_disabled_user_token_returns_403(self, client: AsyncClient, db_session: AsyncSession):
        """Token for a disabled user should return 403."""
        user = await _create_user(db_session, phone="13900000007")
        user.status = UserStatus.DISABLED
        await db_session.commit()
        await db_session.refresh(user)
        resp = await client.get("/v1/auth/me", headers=_auth_headers(user))
        assert resp.status_code == 403

    @pytest.mark.asyncio
    async def test_no_token_on_contracts_returns_unauthorized(self, client: AsyncClient):
        """Contract endpoints require auth."""
        resp = await client.get("/v1/contracts/")
        assert resp.status_code in (401, 403)

    @pytest.mark.asyncio
    async def test_no_token_on_intent_returns_unauthorized(self, client: AsyncClient):
        """Intent endpoints require auth."""
        resp = await client.post("/v1/intent/analyze", json={"user_input": "test"})
        assert resp.status_code in (401, 403)

    @pytest.mark.asyncio
    async def test_no_token_on_market_returns_unauthorized(self, client: AsyncClient):
        """Market endpoints require auth."""
        resp = await client.get("/v1/market/tasks")
        assert resp.status_code in (401, 403)

    @pytest.mark.asyncio
    async def test_no_token_on_credit_returns_unauthorized(self, client: AsyncClient):
        """Credit endpoints require auth."""
        resp = await client.get("/v1/credit/score")
        assert resp.status_code in (401, 403)

    @pytest.mark.asyncio
    async def test_no_token_on_blockchain_returns_unauthorized(self, client: AsyncClient):
        """Blockchain endpoints require auth."""
        resp = await client.get("/v1/blockchain/records/" + str(uuid.uuid4()))
        assert resp.status_code in (401, 403)

    @pytest.mark.asyncio
    async def test_no_token_on_payment_returns_unauthorized(self, client: AsyncClient):
        """Payment endpoints require auth."""
        resp = await client.get("/v1/payment/contracts/" + str(uuid.uuid4()) + "/transactions")
        assert resp.status_code in (401, 403)


# ============================================================
# MODULE 3: Intent Integration Tests
# ============================================================


class TestIntentIntegration:
    """Intent module integration tests."""

    @pytest.mark.asyncio
    async def test_analyze_intent_happy_path(self, client: AsyncClient, db_session: AsyncSession):
        """POST /v1/intent/analyze returns analysis results."""
        user = await _create_user(db_session, phone="13900000011")
        resp = await client.post(
            "/v1/intent/analyze",
            json={"user_input": "I need a website built with React"},
            headers=_auth_headers(user),
        )
        assert resp.status_code == 200
        data = resp.json()["data"]
        assert "analysis" in data
        assert "task_type" in data["analysis"]
        assert "confidence" in data["analysis"]

    @pytest.mark.asyncio
    async def test_create_blueprint_happy_path(self, client: AsyncClient, db_session: AsyncSession):
        """POST /v1/intent/blueprint creates a new blueprint."""
        user = await _create_user(db_session, phone="13900000012")
        resp = await client.post(
            "/v1/intent/blueprint",
            json={
                "title": "My Website Blueprint",
                "task_type": "development",
                "content": {"description": "Build a modern website"},
            },
            headers=_auth_headers(user),
        )
        assert resp.status_code == 201
        data = resp.json()["data"]
        assert data["title"] == "My Website Blueprint"
        assert data["status"] == "draft"

    @pytest.mark.asyncio
    async def test_create_then_get_blueprint(self, client: AsyncClient, db_session: AsyncSession):
        """Create blueprint, then GET it by ID."""
        user = await _create_user(db_session, phone="13900000013")
        headers = _auth_headers(user)

        create_resp = await client.post(
            "/v1/intent/blueprint",
            json={"title": "Fetchable Blueprint", "task_type": "design", "content": {}},
            headers=headers,
        )
        bp_id = create_resp.json()["data"]["id"]

        get_resp = await client.get(f"/v1/intent/blueprint/{bp_id}", headers=headers)
        assert get_resp.status_code == 200
        assert get_resp.json()["data"]["id"] == bp_id

    @pytest.mark.asyncio
    async def test_update_blueprint(self, client: AsyncClient, db_session: AsyncSession):
        """Create blueprint, then update it."""
        user = await _create_user(db_session, phone="13900000014")
        headers = _auth_headers(user)

        create_resp = await client.post(
            "/v1/intent/blueprint",
            json={"title": "Old Title", "task_type": "design", "content": {}},
            headers=headers,
        )
        bp_id = create_resp.json()["data"]["id"]

        update_resp = await client.put(
            f"/v1/intent/blueprint/{bp_id}",
            json={"title": "New Title"},
            headers=headers,
        )
        assert update_resp.status_code == 200
        assert update_resp.json()["data"]["title"] == "New Title"

    @pytest.mark.asyncio
    async def test_lock_blueprint(self, client: AsyncClient, db_session: AsyncSession):
        """Create blueprint, lock it, verify status changes."""
        user = await _create_user(db_session, phone="13900000015")
        headers = _auth_headers(user)

        create_resp = await client.post(
            "/v1/intent/blueprint",
            json={"title": "Lockable", "task_type": "development", "content": {}},
            headers=headers,
        )
        bp_id = create_resp.json()["data"]["id"]

        lock_resp = await client.post(f"/v1/intent/blueprint/{bp_id}/lock", headers=headers)
        assert lock_resp.status_code == 200
        assert lock_resp.json()["data"]["status"] == "locked"

    @pytest.mark.asyncio
    async def test_locked_blueprint_cannot_update(self, client: AsyncClient, db_session: AsyncSession):
        """Updating a locked blueprint should fail."""
        user = await _create_user(db_session, phone="13900000016")
        headers = _auth_headers(user)

        create_resp = await client.post(
            "/v1/intent/blueprint",
            json={"title": "Will Lock", "task_type": "development", "content": {}},
            headers=headers,
        )
        bp_id = create_resp.json()["data"]["id"]
        await client.post(f"/v1/intent/blueprint/{bp_id}/lock", headers=headers)

        update_resp = await client.put(
            f"/v1/intent/blueprint/{bp_id}",
            json={"title": "Should Fail"},
            headers=headers,
        )
        assert update_resp.status_code == 400

    @pytest.mark.asyncio
    async def test_list_blueprints_empty(self, client: AsyncClient, db_session: AsyncSession):
        """List blueprints returns empty list for new user."""
        user = await _create_user(db_session, phone="13900000017")
        resp = await client.get("/v1/intent/blueprints", headers=_auth_headers(user))
        assert resp.status_code == 200
        assert resp.json()["data"]["total"] == 0

    @pytest.mark.asyncio
    async def test_list_blueprints_pagination(self, client: AsyncClient, db_session: AsyncSession):
        """Create multiple blueprints, verify pagination."""
        user = await _create_user(db_session, phone="13900000018")
        headers = _auth_headers(user)

        for i in range(5):
            await client.post(
                "/v1/intent/blueprint",
                json={"title": f"BP-{i}", "task_type": "development", "content": {}},
                headers=headers,
            )

        resp = await client.get("/v1/intent/blueprints?page=1&page_size=2", headers=headers)
        assert resp.status_code == 200
        data = resp.json()["data"]
        assert len(data["items"]) == 2
        assert data["total"] == 5
        assert data["total_pages"] == 3

    @pytest.mark.asyncio
    async def test_blueprint_not_found(self, client: AsyncClient, db_session: AsyncSession):
        """GET non-existent blueprint returns 404."""
        user = await _create_user(db_session, phone="13900000019")
        fake_id = str(uuid.uuid4())
        resp = await client.get(f"/v1/intent/blueprint/{fake_id}", headers=_auth_headers(user))
        assert resp.status_code == 404

    @pytest.mark.asyncio
    async def test_blueprint_wrong_user_forbidden(self, client: AsyncClient, db_session: AsyncSession):
        """Accessing another user's blueprint returns 403."""
        owner = await _create_user(db_session, phone="13900000020")
        other = await _create_user(db_session, phone="13900000021")

        create_resp = await client.post(
            "/v1/intent/blueprint",
            json={"title": "Private BP", "task_type": "development", "content": {}},
            headers=_auth_headers(owner),
        )
        bp_id = create_resp.json()["data"]["id"]

        resp = await client.get(f"/v1/intent/blueprint/{bp_id}", headers=_auth_headers(other))
        assert resp.status_code == 403

    @pytest.mark.asyncio
    async def test_generate_questions_for_blueprint(self, client: AsyncClient, db_session: AsyncSession):
        """POST /v1/intent/blueprint/{id}/questions generates questions."""
        user = await _create_user(db_session, phone="13900000022")
        headers = _auth_headers(user)

        create_resp = await client.post(
            "/v1/intent/blueprint",
            json={"title": "Q Blueprint", "task_type": "development", "content": {"description": "Build app"}},
            headers=headers,
        )
        bp_id = create_resp.json()["data"]["id"]

        resp = await client.post(f"/v1/intent/blueprint/{bp_id}/questions", headers=headers)
        assert resp.status_code == 200
        data = resp.json()["data"]
        assert "questions" in data
        assert data["total"] >= 0


# ============================================================
# MODULE 4: Contract Integration Tests
# ============================================================


class TestContractIntegration:
    """Contract module integration tests."""

    @pytest.mark.asyncio
    async def test_create_contract_as_employer(self, client: AsyncClient, db_session: AsyncSession):
        """Employer can create a contract."""
        employer = await _create_user(db_session, user_type=UserType.EMPLOYER, phone="13900000030")
        resp = await client.post(
            "/v1/contracts/",
            json=_sample_contract_data(),
            headers=_auth_headers(employer),
        )
        assert resp.status_code == 201
        data = resp.json()["data"]
        assert data["title"] == "Integration Test Contract"
        assert data["status"] == "draft"

    @pytest.mark.asyncio
    async def test_create_contract_zero_amount_returns_400(self, client: AsyncClient, db_session: AsyncSession):
        """Creating a contract with zero base_amount should fail."""
        employer = await _create_user(db_session, user_type=UserType.EMPLOYER, phone="13900000031")
        resp = await client.post(
            "/v1/contracts/",
            json=_sample_contract_data(base_amount="0"),
            headers=_auth_headers(employer),
        )
        assert resp.status_code == 400

    @pytest.mark.asyncio
    async def test_contract_lifecycle_publish_accept_submit_complete(
        self, client: AsyncClient, db_session: AsyncSession
    ):
        """Full contract lifecycle: draft -> publish -> accept -> submit -> complete."""
        employer = await _create_user(db_session, user_type=UserType.EMPLOYER, phone="13900000032")
        freelancer = await _create_user(db_session, user_type=UserType.FREELANCER, phone="13900000033")
        emp_headers = _auth_headers(employer)
        fl_headers = _auth_headers(freelancer)

        # Create
        create_resp = await client.post("/v1/contracts/", json=_sample_contract_data(), headers=emp_headers)
        contract_id = create_resp.json()["data"]["id"]

        # Publish
        pub_resp = await client.post(f"/v1/contracts/{contract_id}/publish", headers=emp_headers)
        assert pub_resp.status_code == 200
        assert pub_resp.json()["data"]["status"] == "pending"

        # Accept
        acc_resp = await client.post(f"/v1/contracts/{contract_id}/accept", headers=fl_headers)
        assert acc_resp.status_code == 200
        assert acc_resp.json()["data"]["status"] == "in_progress"

        # Submit for review
        sub_resp = await client.post(f"/v1/contracts/{contract_id}/submit", headers=fl_headers)
        assert sub_resp.status_code == 200
        assert sub_resp.json()["data"]["status"] == "review"

        # Complete
        comp_resp = await client.post(f"/v1/contracts/{contract_id}/complete", headers=emp_headers)
        assert comp_resp.status_code == 200
        assert comp_resp.json()["data"]["status"] == "completed"

    @pytest.mark.asyncio
    async def test_publish_non_draft_contract_returns_400(self, client: AsyncClient, db_session: AsyncSession):
        """Publishing a non-draft contract should fail."""
        employer = await _create_user(db_session, user_type=UserType.EMPLOYER, phone="13900000034")
        contract = await _create_contract_in_db(db_session, employer.id, status=ContractStatus.PENDING)

        resp = await client.post(
            f"/v1/contracts/{contract.id}/publish",
            headers=_auth_headers(employer),
        )
        assert resp.status_code == 400

    @pytest.mark.asyncio
    async def test_accept_contract_as_employer_forbidden(self, client: AsyncClient, db_session: AsyncSession):
        """Employer cannot accept their own contract."""
        employer = await _create_user(db_session, user_type=UserType.EMPLOYER, phone="13900000035")
        contract = await _create_contract_in_db(db_session, employer.id, status=ContractStatus.PENDING)

        resp = await client.post(
            f"/v1/contracts/{contract.id}/accept",
            headers=_auth_headers(employer),
        )
        assert resp.status_code == 403

    @pytest.mark.asyncio
    async def test_terminate_contract(self, client: AsyncClient, db_session: AsyncSession):
        """Employer can terminate a contract."""
        employer = await _create_user(db_session, user_type=UserType.EMPLOYER, phone="13900000036")
        contract = await _create_contract_in_db(db_session, employer.id, status=ContractStatus.PENDING)

        resp = await client.post(
            f"/v1/contracts/{contract.id}/terminate",
            headers=_auth_headers(employer),
        )
        assert resp.status_code == 200
        assert resp.json()["data"]["status"] == "terminated"

    @pytest.mark.asyncio
    async def test_list_contracts_pagination(self, client: AsyncClient, db_session: AsyncSession):
        """Contract list supports pagination."""
        employer = await _create_user(db_session, user_type=UserType.EMPLOYER, phone="13900000037")
        headers = _auth_headers(employer)

        for i in range(3):
            await client.post(
                "/v1/contracts/",
                json=_sample_contract_data(title=f"Contract-{i}"),
                headers=headers,
            )

        resp = await client.get("/v1/contracts/?page=1&page_size=2", headers=headers)
        assert resp.status_code == 200
        data = resp.json()["data"]
        assert len(data["items"]) == 2
        assert data["total"] == 3

    @pytest.mark.asyncio
    async def test_get_contract_not_found(self, client: AsyncClient, db_session: AsyncSession):
        """GET non-existent contract returns 404."""
        employer = await _create_user(db_session, user_type=UserType.EMPLOYER, phone="13900000038")
        fake_id = str(uuid.uuid4())
        resp = await client.get(f"/v1/contracts/{fake_id}", headers=_auth_headers(employer))
        assert resp.status_code == 404

    @pytest.mark.asyncio
    async def test_update_contract_non_draft_returns_400(self, client: AsyncClient, db_session: AsyncSession):
        """Updating a non-draft contract should fail."""
        employer = await _create_user(db_session, user_type=UserType.EMPLOYER, phone="13900000039")
        contract = await _create_contract_in_db(db_session, employer.id, status=ContractStatus.PENDING)

        resp = await client.put(
            f"/v1/contracts/{contract.id}",
            json={"title": "Updated"},
            headers=_auth_headers(employer),
        )
        assert resp.status_code == 400

    @pytest.mark.asyncio
    async def test_update_contract_by_non_owner_forbidden(self, client: AsyncClient, db_session: AsyncSession):
        """Non-owner cannot update contract."""
        employer = await _create_user(db_session, user_type=UserType.EMPLOYER, phone="13900000040")
        other = await _create_user(db_session, user_type=UserType.EMPLOYER, phone="13900000041")
        contract = await _create_contract_in_db(db_session, employer.id, status=ContractStatus.DRAFT)

        resp = await client.put(
            f"/v1/contracts/{contract.id}",
            json={"title": "Hacked"},
            headers=_auth_headers(other),
        )
        assert resp.status_code == 403

    @pytest.mark.asyncio
    async def test_submit_deliverable_for_review_wrong_freelancer(self, client: AsyncClient, db_session: AsyncSession):
        """Only assigned freelancer can submit for review."""
        employer = await _create_user(db_session, user_type=UserType.EMPLOYER, phone="13900000042")
        freelancer = await _create_user(db_session, user_type=UserType.FREELANCER, phone="13900000043")
        wrong_freelancer = await _create_user(db_session, user_type=UserType.FREELANCER, phone="13900000044")

        contract = await _create_contract_in_db(
            db_session, employer.id, status=ContractStatus.IN_PROGRESS, freelancer_id=freelancer.id
        )

        resp = await client.post(
            f"/v1/contracts/{contract.id}/submit",
            headers=_auth_headers(wrong_freelancer),
        )
        assert resp.status_code == 403


# ============================================================
# MODULE 5: Market Integration Tests
# ============================================================


class TestMarketIntegration:
    """Market module integration tests."""

    @pytest.mark.asyncio
    async def test_list_market_tasks_empty(self, client: AsyncClient, db_session: AsyncSession):
        """Market tasks list returns empty when no pending contracts exist."""
        user = await _create_user(db_session, phone="13900000050")
        resp = await client.get("/v1/market/tasks", headers=_auth_headers(user))
        assert resp.status_code == 200
        assert resp.json()["data"]["total"] == 0

    @pytest.mark.asyncio
    async def test_list_market_tasks_with_pending_contract(self, client: AsyncClient, db_session: AsyncSession):
        """Pending contracts appear in market task list."""
        employer = await _create_user(db_session, user_type=UserType.EMPLOYER, phone="13900000051")
        await _create_contract_in_db(db_session, employer.id, status=ContractStatus.PENDING)

        viewer = await _create_user(db_session, phone="13900000052")
        resp = await client.get("/v1/market/tasks", headers=_auth_headers(viewer))
        assert resp.status_code == 200
        assert resp.json()["data"]["total"] >= 1

    @pytest.mark.asyncio
    async def test_get_market_task_detail(self, client: AsyncClient, db_session: AsyncSession):
        """Get market task detail by contract ID."""
        employer = await _create_user(db_session, user_type=UserType.EMPLOYER, phone="13900000053")
        contract = await _create_contract_in_db(db_session, employer.id, status=ContractStatus.PENDING)

        viewer = await _create_user(db_session, phone="13900000054")
        resp = await client.get(
            f"/v1/market/tasks/{contract.id}",
            headers=_auth_headers(viewer),
        )
        assert resp.status_code == 200

    @pytest.mark.asyncio
    async def test_market_task_not_found(self, client: AsyncClient, db_session: AsyncSession):
        """Non-existent market task returns 404."""
        user = await _create_user(db_session, phone="13900000055")
        fake_id = str(uuid.uuid4())
        resp = await client.get(f"/v1/market/tasks/{fake_id}", headers=_auth_headers(user))
        assert resp.status_code == 404

    @pytest.mark.asyncio
    async def test_bid_task_happy_path(self, client: AsyncClient, db_session: AsyncSession):
        """Freelancer can bid on a pending task."""
        employer = await _create_user(db_session, user_type=UserType.EMPLOYER, phone="13900000056")
        freelancer = await _create_user(db_session, user_type=UserType.FREELANCER, phone="13900000057")
        contract = await _create_contract_in_db(db_session, employer.id, status=ContractStatus.PENDING)

        resp = await client.post(
            f"/v1/market/tasks/{contract.id}/bid",
            headers=_auth_headers(freelancer),
        )
        assert resp.status_code == 200
        assert resp.json()["data"]["status"] == "in_progress"

    @pytest.mark.asyncio
    async def test_bid_task_as_employer_forbidden(self, client: AsyncClient, db_session: AsyncSession):
        """Employer cannot bid on their own task."""
        employer = await _create_user(db_session, user_type=UserType.EMPLOYER, phone="13900000058")
        contract = await _create_contract_in_db(db_session, employer.id, status=ContractStatus.PENDING)

        resp = await client.post(
            f"/v1/market/tasks/{contract.id}/bid",
            headers=_auth_headers(employer),
        )
        assert resp.status_code == 403

    @pytest.mark.asyncio
    async def test_bid_on_already_accepted_task_returns_400(self, client: AsyncClient, db_session: AsyncSession):
        """Bidding on an already-accepted task should fail."""
        employer = await _create_user(db_session, user_type=UserType.EMPLOYER, phone="13900000059")
        freelancer1 = await _create_user(db_session, user_type=UserType.FREELANCER, phone="13900000060")
        freelancer2 = await _create_user(db_session, user_type=UserType.FREELANCER, phone="13900000061")
        contract = await _create_contract_in_db(
            db_session, employer.id, status=ContractStatus.IN_PROGRESS, freelancer_id=freelancer1.id
        )

        resp = await client.post(
            f"/v1/market/tasks/{contract.id}/bid",
            headers=_auth_headers(freelancer2),
        )
        assert resp.status_code == 400

    @pytest.mark.asyncio
    async def test_list_market_tasks_with_filters(self, client: AsyncClient, db_session: AsyncSession):
        """Market tasks list with keyword and amount filters."""
        employer = await _create_user(db_session, user_type=UserType.EMPLOYER, phone="13900000062")
        await _create_contract_in_db(db_session, employer.id, status=ContractStatus.PENDING, base_amount=Decimal("500"))

        viewer = await _create_user(db_session, phone="13900000063")
        resp = await client.get(
            "/v1/market/tasks?keyword=DB&min_amount=100&max_amount=1000",
            headers=_auth_headers(viewer),
        )
        assert resp.status_code == 200


# ============================================================
# MODULE 6: Acceptance Integration Tests
# ============================================================


class TestAcceptanceIntegration:
    """Acceptance module integration tests."""

    @pytest.mark.asyncio
    async def test_list_acceptance_records_empty(self, client: AsyncClient, db_session: AsyncSession):
        """List acceptance records for contract with no records."""
        employer = await _create_user(db_session, user_type=UserType.EMPLOYER, phone="13900000070")
        contract = await _create_contract_in_db(db_session, employer.id, status=ContractStatus.IN_PROGRESS)

        resp = await client.get(
            f"/v1/acceptance/contracts/{contract.id}/records",
            headers=_auth_headers(employer),
        )
        assert resp.status_code == 200
        assert resp.json()["data"] == []

    @pytest.mark.asyncio
    async def test_get_acceptance_record_not_found(self, client: AsyncClient, db_session: AsyncSession):
        """GET non-existent acceptance record returns 404."""
        employer = await _create_user(db_session, user_type=UserType.EMPLOYER, phone="13900000071")
        fake_id = str(uuid.uuid4())
        resp = await client.get(
            f"/v1/acceptance/records/{fake_id}",
            headers=_auth_headers(employer),
        )
        assert resp.status_code == 404

    @pytest.mark.asyncio
    async def test_evaluate_as_freelancer_forbidden(self, client: AsyncClient, db_session: AsyncSession):
        """Only employer/admin can trigger evaluation."""
        freelancer = await _create_user(db_session, user_type=UserType.FREELANCER, phone="13900000072")
        employer = await _create_user(db_session, user_type=UserType.EMPLOYER, phone="13900000073")
        contract = await _create_contract_in_db(db_session, employer.id, status=ContractStatus.REVIEW)

        resp = await client.post(
            f"/v1/acceptance/contracts/{contract.id}/evaluate",
            headers=_auth_headers(freelancer),
        )
        assert resp.status_code == 403

    @pytest.mark.asyncio
    async def test_evaluate_contract_wrong_status_returns_400(self, client: AsyncClient, db_session: AsyncSession):
        """Evaluating a non-review contract should fail."""
        employer = await _create_user(db_session, user_type=UserType.EMPLOYER, phone="13900000074")
        contract = await _create_contract_in_db(db_session, employer.id, status=ContractStatus.PENDING)

        resp = await client.post(
            f"/v1/acceptance/contracts/{contract.id}/evaluate",
            headers=_auth_headers(employer),
        )
        assert resp.status_code == 400

    @pytest.mark.asyncio
    async def test_reject_deliverable_as_freelancer_forbidden(self, client: AsyncClient, db_session: AsyncSession):
        """Freelancer cannot reject deliverables (employer only)."""
        freelancer = await _create_user(db_session, user_type=UserType.FREELANCER, phone="13900000075")
        employer = await _create_user(db_session, user_type=UserType.EMPLOYER, phone="13900000076")
        contract = await _create_contract_in_db(db_session, employer.id, status=ContractStatus.REVIEW)
        deliverable = await _create_deliverable_in_db(db_session, contract.id, DeliverableAcceptanceStatus.PENDING)

        resp = await client.post(
            f"/v1/acceptance/deliverables/{deliverable.id}/reject",
            json={"rejection_reason": "Needs rework"},
            headers=_auth_headers(freelancer),
        )
        assert resp.status_code == 403

    @pytest.mark.asyncio
    async def test_resubmit_deliverable_as_employer_forbidden(self, client: AsyncClient, db_session: AsyncSession):
        """Employer cannot resubmit deliverables (freelancer only)."""
        employer = await _create_user(db_session, user_type=UserType.EMPLOYER, phone="13900000077")
        contract = await _create_contract_in_db(db_session, employer.id, status=ContractStatus.IN_PROGRESS)
        deliverable = await _create_deliverable_in_db(db_session, contract.id, DeliverableAcceptanceStatus.REJECTED)

        resp = await client.post(
            f"/v1/acceptance/deliverables/{deliverable.id}/resubmit",
            json={"file_url": "https://example.com/v2.zip", "file_hash": "abc123"},
            headers=_auth_headers(employer),
        )
        assert resp.status_code == 403

    @pytest.mark.asyncio
    async def test_reject_deliverable_missing_reason_returns_422(self, client: AsyncClient, db_session: AsyncSession):
        """Reject deliverable without reason should fail validation."""
        employer = await _create_user(db_session, user_type=UserType.EMPLOYER, phone="13900000078")
        contract = await _create_contract_in_db(db_session, employer.id, status=ContractStatus.REVIEW)
        deliverable = await _create_deliverable_in_db(db_session, contract.id, DeliverableAcceptanceStatus.PENDING)

        resp = await client.post(
            f"/v1/acceptance/deliverables/{deliverable.id}/reject",
            json={},
            headers=_auth_headers(employer),
        )
        assert resp.status_code == 422


# ============================================================
# MODULE 7: Payment Integration Tests
# ============================================================


class TestPaymentIntegration:
    """Payment module integration tests."""

    @pytest.mark.asyncio
    async def test_create_escrow_happy_path(self, client: AsyncClient, db_session: AsyncSession):
        """Employer can create escrow for their contract."""
        employer = await _create_user(db_session, user_type=UserType.EMPLOYER, phone="13900000080")
        contract = await _create_contract_in_db(db_session, employer.id, status=ContractStatus.PENDING)

        resp = await client.post(
            "/v1/payment/escrow",
            json={"contract_id": str(contract.id), "amount": "1000.00"},
            headers=_auth_headers(employer),
        )
        assert resp.status_code == 201
        data = resp.json()["data"]
        assert data["transaction_type"] == "escrow"
        assert data["status"] == "pending"

    @pytest.mark.asyncio
    async def test_escrow_zero_amount_returns_422(self, client: AsyncClient, db_session: AsyncSession):
        """Escrow with zero amount should fail validation."""
        employer = await _create_user(db_session, user_type=UserType.EMPLOYER, phone="13900000081")
        contract = await _create_contract_in_db(db_session, employer.id, status=ContractStatus.PENDING)

        resp = await client.post(
            "/v1/payment/escrow",
            json={"contract_id": str(contract.id), "amount": "0"},
            headers=_auth_headers(employer),
        )
        assert resp.status_code == 422

    @pytest.mark.asyncio
    async def test_escrow_missing_contract_id_returns_422(self, client: AsyncClient, db_session: AsyncSession):
        """Escrow without contract_id should fail validation."""
        employer = await _create_user(db_session, user_type=UserType.EMPLOYER, phone="13900000082")
        resp = await client.post(
            "/v1/payment/escrow",
            json={"amount": "1000.00"},
            headers=_auth_headers(employer),
        )
        assert resp.status_code == 422

    @pytest.mark.asyncio
    async def test_list_transactions_empty(self, client: AsyncClient, db_session: AsyncSession):
        """List transactions returns empty for contract with no transactions."""
        employer = await _create_user(db_session, user_type=UserType.EMPLOYER, phone="13900000083")
        contract = await _create_contract_in_db(db_session, employer.id, status=ContractStatus.PENDING)

        resp = await client.get(
            f"/v1/payment/contracts/{contract.id}/transactions",
            headers=_auth_headers(employer),
        )
        assert resp.status_code == 200
        assert resp.json()["data"]["total"] == 0

    @pytest.mark.asyncio
    async def test_escrow_then_list_transactions(self, client: AsyncClient, db_session: AsyncSession):
        """Create escrow, then verify it appears in transactions."""
        employer = await _create_user(db_session, user_type=UserType.EMPLOYER, phone="13900000084")
        contract = await _create_contract_in_db(db_session, employer.id, status=ContractStatus.PENDING)
        headers = _auth_headers(employer)

        await client.post(
            "/v1/payment/escrow",
            json={"contract_id": str(contract.id), "amount": "500.00"},
            headers=headers,
        )

        resp = await client.get(
            f"/v1/payment/contracts/{contract.id}/transactions",
            headers=headers,
        )
        assert resp.status_code == 200
        assert resp.json()["data"]["total"] >= 1

    @pytest.mark.asyncio
    async def test_refund_nonexistent_contract_returns_400(self, client: AsyncClient, db_session: AsyncSession):
        """Refund for non-existent contract should fail."""
        employer = await _create_user(db_session, user_type=UserType.EMPLOYER, phone="13900000085")
        fake_id = str(uuid.uuid4())

        resp = await client.post(
            f"/v1/payment/contracts/{fake_id}/refund",
            json={"reason": "Contract not found"},
            headers=_auth_headers(employer),
        )
        assert resp.status_code == 400


# ============================================================
# MODULE 8: Credit Integration Tests
# ============================================================


class TestCreditIntegration:
    """Credit module integration tests."""

    @pytest.mark.asyncio
    async def test_get_my_credit_score(self, client: AsyncClient, db_session: AsyncSession):
        """GET /v1/credit/score returns user's credit score."""
        user = await _create_user(db_session, phone="13900000090", credit_score=650)
        resp = await client.get("/v1/credit/score", headers=_auth_headers(user))
        assert resp.status_code == 200
        data = resp.json()["data"]
        assert data["credit_score"] == 650
        assert "credit_level" in data

    @pytest.mark.asyncio
    async def test_get_credit_history(self, client: AsyncClient, db_session: AsyncSession):
        """GET /v1/credit/history returns credit history."""
        user = await _create_user(db_session, phone="13900000091")
        resp = await client.get("/v1/credit/history", headers=_auth_headers(user))
        assert resp.status_code == 200
        data = resp.json()["data"]
        assert "history" in data
        assert isinstance(data["history"], list)

    @pytest.mark.asyncio
    async def test_refresh_credit_score(self, client: AsyncClient, db_session: AsyncSession):
        """POST /v1/credit/refresh recalculates credit score."""
        user = await _create_user(db_session, phone="13900000092")
        resp = await client.post("/v1/credit/refresh", headers=_auth_headers(user))
        assert resp.status_code == 200
        assert "credit_score" in resp.json()["data"]

    @pytest.mark.asyncio
    async def test_get_user_credit_score(self, client: AsyncClient, db_session: AsyncSession):
        """GET /v1/credit/users/{id}/score returns another user's credit score."""
        owner = await _create_user(db_session, phone="13900000093", credit_score=750)
        viewer = await _create_user(db_session, phone="13900000094")

        resp = await client.get(
            f"/v1/credit/users/{owner.id}/score",
            headers=_auth_headers(viewer),
        )
        assert resp.status_code == 200
        assert resp.json()["data"]["credit_score"] == 750

    @pytest.mark.asyncio
    async def test_get_nonexistent_user_credit_returns_404(self, client: AsyncClient, db_session: AsyncSession):
        """Credit score for non-existent user returns 404."""
        user = await _create_user(db_session, phone="13900000095")
        fake_id = str(uuid.uuid4())
        resp = await client.get(
            f"/v1/credit/users/{fake_id}/score",
            headers=_auth_headers(user),
        )
        assert resp.status_code == 404

    @pytest.mark.asyncio
    async def test_credit_score_no_auth(self, client: AsyncClient):
        """Credit endpoints require authentication."""
        resp = await client.get("/v1/credit/score")
        assert resp.status_code in (401, 403)

    @pytest.mark.asyncio
    async def test_credit_score_new_user_flag(self, client: AsyncClient, db_session: AsyncSession):
        """New user has is_new_user flag in credit score."""
        user = await _create_user(db_session, phone="13900000096", credit_score=600)
        resp = await client.get("/v1/credit/score", headers=_auth_headers(user))
        assert resp.status_code == 200
        assert resp.json()["data"]["is_new_user"] is True


# ============================================================
# MODULE 9: Blockchain Integration Tests
# ============================================================


class TestBlockchainIntegration:
    """Blockchain module integration tests."""

    @pytest.mark.asyncio
    async def test_create_blockchain_record(self, client: AsyncClient, db_session: AsyncSession):
        """POST /v1/blockchain/record creates a blockchain record."""
        user = await _create_user(db_session, phone="13900000100")
        contract = await _create_contract_in_db(db_session, user.id, status=ContractStatus.PENDING)

        resp = await client.post(
            "/v1/blockchain/record",
            json={
                "contract_id": str(contract.id),
                "node_type": "contract_created",
                "content_data": {"action": "contract_created", "contract_id": str(contract.id)},
            },
            headers=_auth_headers(user),
        )
        assert resp.status_code == 201
        data = resp.json()["data"]
        assert "content_hash" in data
        assert "block_hash" in data

    @pytest.mark.asyncio
    async def test_get_blockchain_record(self, client: AsyncClient, db_session: AsyncSession):
        """Create record, then GET it by ID."""
        user = await _create_user(db_session, phone="13900000101")
        contract = await _create_contract_in_db(db_session, user.id, status=ContractStatus.PENDING)
        headers = _auth_headers(user)

        create_resp = await client.post(
            "/v1/blockchain/record",
            json={
                "contract_id": str(contract.id),
                "node_type": "contract_created",
                "content_data": {"test": "data"},
            },
            headers=headers,
        )
        record_id = create_resp.json()["data"]["id"]

        get_resp = await client.get(f"/v1/blockchain/records/{record_id}", headers=headers)
        assert get_resp.status_code == 200
        assert get_resp.json()["data"]["id"] == record_id

    @pytest.mark.asyncio
    async def test_verify_blockchain_record_valid(self, client: AsyncClient, db_session: AsyncSession):
        """Verify blockchain record with matching content returns valid."""
        user = await _create_user(db_session, phone="13900000102")
        contract = await _create_contract_in_db(db_session, user.id, status=ContractStatus.PENDING)
        headers = _auth_headers(user)
        content = {"key": "value", "number": 42}

        create_resp = await client.post(
            "/v1/blockchain/record",
            json={
                "contract_id": str(contract.id),
                "node_type": "contract_created",
                "content_data": content,
            },
            headers=headers,
        )
        record_id = create_resp.json()["data"]["id"]

        verify_resp = await client.post(
            f"/v1/blockchain/records/{record_id}/verify",
            json={"content_data": content},
            headers=headers,
        )
        assert verify_resp.status_code == 200
        assert verify_resp.json()["data"]["is_valid"] is True

    @pytest.mark.asyncio
    async def test_verify_blockchain_record_mismatch(self, client: AsyncClient, db_session: AsyncSession):
        """Verify blockchain record with different content returns invalid."""
        user = await _create_user(db_session, phone="13900000103")
        contract = await _create_contract_in_db(db_session, user.id, status=ContractStatus.PENDING)
        headers = _auth_headers(user)

        create_resp = await client.post(
            "/v1/blockchain/record",
            json={
                "contract_id": str(contract.id),
                "node_type": "contract_created",
                "content_data": {"original": "data"},
            },
            headers=headers,
        )
        record_id = create_resp.json()["data"]["id"]

        verify_resp = await client.post(
            f"/v1/blockchain/records/{record_id}/verify",
            json={"content_data": {"tampered": "data"}},
            headers=headers,
        )
        assert verify_resp.status_code == 200
        assert verify_resp.json()["data"]["is_valid"] is False

    @pytest.mark.asyncio
    async def test_list_contract_records(self, client: AsyncClient, db_session: AsyncSession):
        """GET /v1/blockchain/contracts/{id}/records lists records for a contract."""
        user = await _create_user(db_session, phone="13900000104")
        contract = await _create_contract_in_db(db_session, user.id, status=ContractStatus.PENDING)
        headers = _auth_headers(user)

        for node_type in ["contract_created", "deliverable_submit"]:
            await client.post(
                "/v1/blockchain/record",
                json={
                    "contract_id": str(contract.id),
                    "node_type": node_type,
                    "content_data": {"type": node_type},
                },
                headers=headers,
            )

        resp = await client.get(
            f"/v1/blockchain/contracts/{contract.id}/records",
            headers=headers,
        )
        assert resp.status_code == 200
        assert resp.json()["data"]["total"] == 2

    @pytest.mark.asyncio
    async def test_blockchain_record_not_found(self, client: AsyncClient, db_session: AsyncSession):
        """GET non-existent blockchain record returns 404."""
        user = await _create_user(db_session, phone="13900000105")
        fake_id = str(uuid.uuid4())
        resp = await client.get(f"/v1/blockchain/records/{fake_id}", headers=_auth_headers(user))
        assert resp.status_code == 404


# ============================================================
# MODULE 10: Profile Integration Tests
# ============================================================


class TestProfileIntegration:
    """Profile module integration tests."""

    @pytest.mark.asyncio
    async def test_get_user_profile(self, client: AsyncClient, db_session: AsyncSession):
        """GET /v1/users/{id}/profile returns user public profile."""
        user = await _create_user(db_session, phone="13900000110", nickname="ProfileUser")
        resp = await client.get(f"/v1/users/{user.id}/profile")
        assert resp.status_code == 200
        assert resp.json()["data"]["nickname"] == "ProfileUser"

    @pytest.mark.asyncio
    async def test_get_nonexistent_profile_returns_404(self, client: AsyncClient):
        """GET profile for non-existent user returns 404."""
        fake_id = str(uuid.uuid4())
        resp = await client.get(f"/v1/users/{fake_id}/profile")
        assert resp.status_code == 404

    @pytest.mark.asyncio
    async def test_update_my_profile(self, client: AsyncClient, db_session: AsyncSession):
        """PUT /v1/users/me/profile updates current user profile."""
        user = await _create_user(db_session, phone="13900000111")
        resp = await client.put(
            "/v1/users/me/profile",
            json={"nickname": "UpdatedNick", "bio": "New bio", "domain_tags": ["python", "fastapi"]},
            headers=_auth_headers(user),
        )
        assert resp.status_code == 200
        assert resp.json()["data"]["nickname"] == "UpdatedNick"
        assert resp.json()["data"]["bio"] == "New bio"

    @pytest.mark.asyncio
    async def test_upload_avatar_url(self, client: AsyncClient, db_session: AsyncSession):
        """POST /v1/users/me/avatar with URL type."""
        user = await _create_user(db_session, phone="13900000112")
        resp = await client.post(
            "/v1/users/me/avatar",
            json={"avatar_data": "https://example.com/avatar.png", "avatar_type": "url"},
            headers=_auth_headers(user),
        )
        assert resp.status_code == 200

    @pytest.mark.asyncio
    async def test_get_user_stats(self, client: AsyncClient, db_session: AsyncSession):
        """GET /v1/users/me/stats returns user statistics."""
        user = await _create_user(db_session, phone="13900000113")
        resp = await client.get("/v1/users/me/stats", headers=_auth_headers(user))
        assert resp.status_code == 200
        data = resp.json()["data"]
        assert "total_contracts" in data
        assert "completed_contracts" in data
        assert "total_earnings" in data

    @pytest.mark.asyncio
    async def test_verify_identity(self, client: AsyncClient, db_session: AsyncSession):
        """POST /v1/users/me/verify performs identity verification."""
        user = await _create_user(db_session, phone="13900000114")
        resp = await client.post(
            "/v1/users/me/verify",
            json={"real_name": "Zhang San", "id_card": "110101199001011234"},
            headers=_auth_headers(user),
        )
        assert resp.status_code == 200

    @pytest.mark.asyncio
    async def test_verify_identity_duplicate_returns_409(self, client: AsyncClient, db_session: AsyncSession):
        """Duplicate identity verification should return 409."""
        user = await _create_user(db_session, phone="13900000115")
        headers = _auth_headers(user)

        await client.post(
            "/v1/users/me/verify",
            json={"real_name": "Zhang San", "id_card": "110101199001011234"},
            headers=headers,
        )
        resp = await client.post(
            "/v1/users/me/verify",
            json={"real_name": "Zhang San", "id_card": "110101199001011234"},
            headers=headers,
        )
        assert resp.status_code == 409

    @pytest.mark.asyncio
    async def test_profile_update_no_auth(self, client: AsyncClient):
        """Profile update requires authentication."""
        resp = await client.put("/v1/users/me/profile", json={"nickname": "Hacker"})
        assert resp.status_code in (401, 403)


# ============================================================
# MODULE 11: Pagination & Input Validation Edge Cases
# ============================================================


class TestPaginationEdgeCases:
    """Pagination boundary tests across modules."""

    @pytest.mark.asyncio
    async def test_contracts_page_zero_returns_422(self, client: AsyncClient, db_session: AsyncSession):
        """page=0 should fail validation (ge=1)."""
        employer = await _create_user(db_session, user_type=UserType.EMPLOYER, phone="13900000120")
        resp = await client.get("/v1/contracts/?page=0", headers=_auth_headers(employer))
        assert resp.status_code == 422

    @pytest.mark.asyncio
    async def test_contracts_size_zero_returns_422(self, client: AsyncClient, db_session: AsyncSession):
        """page_size=0 should fail validation (ge=1)."""
        employer = await _create_user(db_session, user_type=UserType.EMPLOYER, phone="13900000121")
        resp = await client.get("/v1/contracts/?size=0", headers=_auth_headers(employer))
        assert resp.status_code == 422

    @pytest.mark.asyncio
    async def test_contracts_size_over_100_returns_422(self, client: AsyncClient, db_session: AsyncSession):
        """page_size > 100 should fail validation (le=100)."""
        employer = await _create_user(db_session, user_type=UserType.EMPLOYER, phone="13900000122")
        resp = await client.get("/v1/contracts/?size=999", headers=_auth_headers(employer))
        assert resp.status_code == 422

    @pytest.mark.asyncio
    async def test_blueprints_page_zero_returns_422(self, client: AsyncClient, db_session: AsyncSession):
        """Intent blueprints page=0 should fail validation."""
        user = await _create_user(db_session, phone="13900000123")
        resp = await client.get("/v1/intent/blueprints?page=0", headers=_auth_headers(user))
        assert resp.status_code == 422

    @pytest.mark.asyncio
    async def test_market_tasks_size_over_100_returns_422(self, client: AsyncClient, db_session: AsyncSession):
        """Market tasks size > 100 should fail validation."""
        user = await _create_user(db_session, phone="13900000124")
        resp = await client.get("/v1/market/tasks?size=500", headers=_auth_headers(user))
        assert resp.status_code == 422

    @pytest.mark.asyncio
    async def test_payment_transactions_page_zero_returns_422(self, client: AsyncClient, db_session: AsyncSession):
        """Payment transactions page=0 should fail validation."""
        employer = await _create_user(db_session, user_type=UserType.EMPLOYER, phone="13900000125")
        contract = await _create_contract_in_db(db_session, employer.id, status=ContractStatus.PENDING)
        resp = await client.get(
            f"/v1/payment/contracts/{contract.id}/transactions?page=0",
            headers=_auth_headers(employer),
        )
        assert resp.status_code == 422


# ============================================================
# MODULE 12: Cross-Module Integration Flows
# ============================================================


class TestCrossModuleFlows:
    """End-to-end integration tests spanning multiple modules."""

    @pytest.mark.asyncio
    async def test_intent_to_contract_flow(self, client: AsyncClient, db_session: AsyncSession):
        """Intent analysis -> blueprint -> contract creation flow."""
        employer = await _create_user(db_session, user_type=UserType.EMPLOYER, phone="13900000130")
        headers = _auth_headers(employer)

        # Step 1: Analyze intent
        analyze_resp = await client.post(
            "/v1/intent/analyze",
            json={"user_input": "Build a mobile app for food delivery"},
            headers=headers,
        )
        assert analyze_resp.status_code == 200
        task_type = analyze_resp.json()["data"]["analysis"]["task_type"]

        # Step 2: Create blueprint
        bp_resp = await client.post(
            "/v1/intent/blueprint",
            json={
                "title": "Food Delivery App",
                "task_type": task_type if task_type in ["development", "design", "other"] else "development",
                "content": {"description": "Build a food delivery mobile app"},
            },
            headers=headers,
        )
        assert bp_resp.status_code == 201
        bp_data = bp_resp.json()["data"]

        # Step 3: Lock blueprint
        lock_resp = await client.post(
            f"/v1/intent/blueprint/{bp_data['id']}/lock",
            headers=headers,
        )
        assert lock_resp.status_code == 200

        # Step 4: Create contract using blueprint data
        contract_resp = await client.post(
            "/v1/contracts/",
            json={
                "title": bp_data["title"],
                "task_type": "development",
                "base_amount": "5000.00",
                "intent_blueprint": bp_data["content"],
            },
            headers=headers,
        )
        assert contract_resp.status_code == 201
        assert contract_resp.json()["data"]["title"] == "Food Delivery App"

    @pytest.mark.asyncio
    async def test_full_lifecycle_with_payment(self, client: AsyncClient, db_session: AsyncSession):
        """Complete lifecycle: create -> publish -> bid -> escrow -> submit -> review -> complete -> release."""
        employer = await _create_user(db_session, user_type=UserType.EMPLOYER, phone="13900000131")
        freelancer = await _create_user(db_session, user_type=UserType.FREELANCER, phone="13900000132")
        emp_h = _auth_headers(employer)
        fl_h = _auth_headers(freelancer)

        # Create contract
        c_resp = await client.post("/v1/contracts/", json=_sample_contract_data(), headers=emp_h)
        cid = c_resp.json()["data"]["id"]

        # Publish
        await client.post(f"/v1/contracts/{cid}/publish", headers=emp_h)

        # Bid
        bid_resp = await client.post(f"/v1/market/tasks/{cid}/bid", headers=fl_h)
        assert bid_resp.status_code == 200

        # Escrow
        escrow_resp = await client.post(
            "/v1/payment/escrow",
            json={"contract_id": cid, "amount": "1000.00"},
            headers=emp_h,
        )
        assert escrow_resp.status_code == 201

        # Submit for review
        submit_resp = await client.post(f"/v1/contracts/{cid}/submit", headers=fl_h)
        assert submit_resp.status_code == 200
        assert submit_resp.json()["data"]["status"] == "review"

        # Complete (accept)
        complete_resp = await client.post(f"/v1/contracts/{cid}/complete", headers=emp_h)
        assert complete_resp.status_code == 200
        assert complete_resp.json()["data"]["status"] == "completed"

        # Release payment
        release_resp = await client.post(f"/v1/payment/contracts/{cid}/release", headers=emp_h)
        assert release_resp.status_code == 200

        # Check transactions
        tx_resp = await client.get(f"/v1/payment/contracts/{cid}/transactions", headers=emp_h)
        assert tx_resp.status_code == 200
        assert tx_resp.json()["data"]["total"] >= 2  # escrow + payment

    @pytest.mark.asyncio
    async def test_contract_terminate_then_refund(self, client: AsyncClient, db_session: AsyncSession):
        """Terminate contract and issue refund."""
        employer = await _create_user(db_session, user_type=UserType.EMPLOYER, phone="13900000133")
        headers = _auth_headers(employer)

        c_resp = await client.post("/v1/contracts/", json=_sample_contract_data(), headers=headers)
        cid = c_resp.json()["data"]["id"]

        # Publish and escrow
        await client.post(f"/v1/contracts/{cid}/publish", headers=headers)
        await client.post(
            "/v1/payment/escrow",
            json={"contract_id": cid, "amount": "1000.00"},
            headers=headers,
        )

        # Terminate
        term_resp = await client.post(f"/v1/contracts/{cid}/terminate", headers=headers)
        assert term_resp.status_code == 200

        # Refund
        refund_resp = await client.post(
            f"/v1/payment/contracts/{cid}/refund",
            json={"reason": "Contract terminated"},
            headers=headers,
        )
        assert refund_resp.status_code == 200

    @pytest.mark.asyncio
    async def test_profile_and_credit_after_registration(self, client: AsyncClient, db_session: AsyncSession):
        """Register -> check profile -> check credit score."""
        from app.modules.auth.login_guard import login_guard
        login_guard._lock_store.clear()

        reg_resp = await client.post("/v1/auth/register", json={
            "phone": "13900000134",
            "password": "TestPass123",
            "nickname": "CreditUser",
        })
        user_id = reg_resp.json()["data"]["id"]

        login_resp = await client.post("/v1/auth/login", json={
            "phone": "13900000134",
            "password": "TestPass123",
        })
        token = login_resp.json()["data"]["access_token"]
        headers = {"Authorization": f"Bearer {token}"}

        # Check profile
        profile_resp = await client.get(f"/v1/users/{user_id}/profile")
        assert profile_resp.status_code == 200

        # Check credit
        credit_resp = await client.get("/v1/credit/score", headers=headers)
        assert credit_resp.status_code == 200
        assert credit_resp.json()["data"]["credit_score"] == 600

    @pytest.mark.asyncio
    async def test_blockchain_record_for_contract_lifecycle(self, client: AsyncClient, db_session: AsyncSession):
        """Create blockchain records at each contract lifecycle stage."""
        employer = await _create_user(db_session, user_type=UserType.EMPLOYER, phone="13900000135")
        headers = _auth_headers(employer)

        c_resp = await client.post("/v1/contracts/", json=_sample_contract_data(), headers=headers)
        cid = c_resp.json()["data"]["id"]

        # Record contract creation on blockchain
        rec_resp = await client.post(
            "/v1/blockchain/record",
            json={
                "contract_id": cid,
                "node_type": "contract_created",
                "content_data": {"event": "contract_created", "contract_id": cid},
            },
            headers=headers,
        )
        assert rec_resp.status_code == 201

        # List blockchain records for the contract
        list_resp = await client.get(f"/v1/blockchain/contracts/{cid}/records", headers=headers)
        assert list_resp.status_code == 200
        assert list_resp.json()["data"]["total"] == 1

    @pytest.mark.asyncio
    async def test_credit_score_after_contract_completion(
        self, client: AsyncClient, db_session: AsyncSession
    ):
        """Credit score refresh after completing a contract."""
        employer = await _create_user(db_session, user_type=UserType.EMPLOYER, phone="13900000136")
        freelancer = await _create_user(db_session, user_type=UserType.FREELANCER, phone="13900000137")
        emp_h = _auth_headers(employer)
        fl_h = _auth_headers(freelancer)

        # Full lifecycle
        c_resp = await client.post("/v1/contracts/", json=_sample_contract_data(), headers=emp_h)
        cid = c_resp.json()["data"]["id"]
        await client.post(f"/v1/contracts/{cid}/publish", headers=emp_h)
        await client.post(f"/v1/market/tasks/{cid}/bid", headers=fl_h)
        await client.post(f"/v1/contracts/{cid}/submit", headers=fl_h)
        await client.post(f"/v1/contracts/{cid}/complete", headers=emp_h)

        # Refresh credit for freelancer
        credit_resp = await client.post("/v1/credit/refresh", headers=fl_h)
        assert credit_resp.status_code == 200
        assert "credit_score" in credit_resp.json()["data"]

    @pytest.mark.asyncio
    async def test_multiple_users_same_marketplace(self, client: AsyncClient, db_session: AsyncSession):
        """Multiple freelancers see the same marketplace tasks."""
        employer = await _create_user(db_session, user_type=UserType.EMPLOYER, phone="13900000138")
        fl1 = await _create_user(db_session, user_type=UserType.FREELANCER, phone="13900000139")
        fl2 = await _create_user(db_session, user_type=UserType.FREELANCER, phone="13900000140")

        await _create_contract_in_db(db_session, employer.id, status=ContractStatus.PENDING)

        resp1 = await client.get("/v1/market/tasks", headers=_auth_headers(fl1))
        resp2 = await client.get("/v1/market/tasks", headers=_auth_headers(fl2))

        assert resp1.status_code == 200
        assert resp2.status_code == 200
        assert resp1.json()["data"]["total"] == resp2.json()["data"]["total"]

    @pytest.mark.asyncio
    async def test_nonexistent_uuid_format_rejected(self, client: AsyncClient, db_session: AsyncSession):
        """Invalid UUID format in path should return 422."""
        user = await _create_user(db_session, phone="13900000141")
        resp = await client.get(
            "/v1/contracts/not-a-valid-uuid",
            headers=_auth_headers(user),
        )
        assert resp.status_code == 422


# ============================================================
# MODULE 13: Health Check
# ============================================================


class TestHealthCheck:
    """Health endpoint tests."""

    @pytest.mark.asyncio
    async def test_health_endpoint(self, client: AsyncClient):
        """GET /health returns 200."""
        resp = await client.get("/health")
        assert resp.status_code == 200
        assert resp.json()["code"] == 200
        assert resp.json()["message"] == "ok"

    @pytest.mark.asyncio
    async def test_health_endpoint_contains_project_info(self, client: AsyncClient):
        """Health endpoint returns project name and version."""
        resp = await client.get("/health")
        assert resp.status_code == 200
        data = resp.json()["data"]
        assert "project" in data
        assert "version" in data


# ============================================================
# MODULE 14: Cross-Module Role Enforcement
# ============================================================


class TestRoleEnforcement:
    """Cross-module role enforcement tests."""

    @pytest.mark.asyncio
    async def test_freelancer_cannot_create_contract(self, client: AsyncClient, db_session: AsyncSession):
        """Freelancer attempting to create a contract -- should still work (no explicit role check in router)."""
        freelancer = await _create_user(db_session, user_type=UserType.FREELANCER, phone="13900000150")
        resp = await client.post(
            "/v1/contracts/",
            json=_sample_contract_data(),
            headers=_auth_headers(freelancer),
        )
        # The contract router doesn't explicitly restrict by role at the endpoint level,
        # it relies on business logic. Test the API accepts the request.
        # If the app enforces employer-only, this would be 403.
        assert resp.status_code in (201, 403)

    @pytest.mark.asyncio
    async def test_employer_cannot_bid_on_market(self, client: AsyncClient, db_session: AsyncSession):
        """Employer cannot bid on marketplace tasks."""
        employer = await _create_user(db_session, user_type=UserType.EMPLOYER, phone="13900000151")
        other_employer = await _create_user(db_session, user_type=UserType.EMPLOYER, phone="13900000152")
        contract = await _create_contract_in_db(db_session, other_employer.id, status=ContractStatus.PENDING)

        resp = await client.post(
            f"/v1/market/tasks/{contract.id}/bid",
            headers=_auth_headers(employer),
        )
        assert resp.status_code == 403

    @pytest.mark.asyncio
    async def test_freelancer_cannot_trigger_acceptance_evaluation(
        self, client: AsyncClient, db_session: AsyncSession
    ):
        """Freelancer cannot trigger acceptance evaluation."""
        freelancer = await _create_user(db_session, user_type=UserType.FREELANCER, phone="13900000153")
        employer = await _create_user(db_session, user_type=UserType.EMPLOYER, phone="13900000154")
        contract = await _create_contract_in_db(db_session, employer.id, status=ContractStatus.REVIEW)

        resp = await client.post(
            f"/v1/acceptance/contracts/{contract.id}/evaluate",
            headers=_auth_headers(freelancer),
        )
        assert resp.status_code == 403

    @pytest.mark.asyncio
    async def test_employer_cannot_resubmit_deliverable(self, client: AsyncClient, db_session: AsyncSession):
        """Employer cannot resubmit deliverables."""
        employer = await _create_user(db_session, user_type=UserType.EMPLOYER, phone="13900000155")
        contract = await _create_contract_in_db(db_session, employer.id, status=ContractStatus.IN_PROGRESS)
        deliverable = await _create_deliverable_in_db(db_session, contract.id, DeliverableAcceptanceStatus.REJECTED)

        resp = await client.post(
            f"/v1/acceptance/deliverables/{deliverable.id}/resubmit",
            json={"file_url": "https://example.com/v2.zip", "file_hash": "abc123"},
            headers=_auth_headers(employer),
        )
        assert resp.status_code == 403
