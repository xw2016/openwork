"""
用户资料模块单元测试
测试 profile CRUD、实名认证、头像上传等
"""

from __future__ import annotations

import base64
import uuid
from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.models.user import User, UserStatus, UserType
from app.modules.profile.service import (
    get_user_profile,
    get_user_stats,
    update_profile,
    upload_avatar,
    verify_identity,
)
from app.schemas.user import (
    AvatarUploadRequest,
    ProfileUpdateRequest,
    VerifyRequest,
)


# ============================================================
# 辅助函数
# ============================================================

def _make_user(
    user_id: uuid.UUID | None = None,
    nickname: str = "测试用户",
    user_type: UserType = UserType.FREELANCER,
    bio: str | None = None,
    domain_tags: list | None = None,
    avatar_url: str | None = None,
    verified_at: datetime | None = None,
    credit_score: int = 600,
) -> User:
    """创建测试用户对象"""
    user = User.__new__(User)
    user.id = user_id or uuid.uuid4()
    user.user_type = user_type
    user.nickname = nickname
    user.avatar = None
    user.avatar_url = avatar_url
    phone = f"1380000{str(user.id)[:4]}"
    user.phone = phone
    user.email = None
    user.real_name = None
    user.id_card = None
    user.bio = bio
    user.domain_tags = domain_tags or []
    user.verified_at = verified_at
    user.credit_score = credit_score
    user.credit_detail = {}
    user.status = UserStatus.ACTIVE
    user.hashed_password = "hashed"
    user.created_at = datetime.now(timezone.utc)
    user.updated_at = datetime.now(timezone.utc)
    return user


def _make_mock_db() -> AsyncMock:
    """创建模拟数据库 session"""
    db = AsyncMock()
    db.commit = AsyncMock()
    db.refresh = AsyncMock()
    return db


# ============================================================
# 测试：获取用户资料
# ============================================================

class TestGetUserProfile:
    """测试 get_user_profile"""

    @pytest.mark.asyncio
    async def test_get_existing_user_profile(self):
        """获取存在的用户资料"""
        user = _make_user(nickname="张三", bio="全栈工程师")
        db = _make_mock_db()
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = user
        db.execute = AsyncMock(return_value=mock_result)

        result = await get_user_profile(db, user.id)

        assert result is not None
        assert result.nickname == "张三"
        assert result.bio == "全栈工程师"

    @pytest.mark.asyncio
    async def test_get_nonexistent_user_profile(self):
        """获取不存在的用户资料返回 None"""
        db = _make_mock_db()
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = None
        db.execute = AsyncMock(return_value=mock_result)

        result = await get_user_profile(db, uuid.uuid4())

        assert result is None


# ============================================================
# 测试：更新用户资料
# ============================================================

class TestUpdateProfile:
    """测试 update_profile"""

    @pytest.mark.asyncio
    async def test_update_nickname_and_bio(self):
        """更新昵称和简介"""
        user = _make_user(nickname="旧昵称")
        db = _make_mock_db()
        data = ProfileUpdateRequest(nickname="新昵称", bio="新简介")

        result = await update_profile(db, user, data)

        assert result.nickname == "新昵称"
        assert result.bio == "新简介"
        db.commit.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_update_domain_tags(self):
        """更新领域标签"""
        user = _make_user()
        db = _make_mock_db()
        data = ProfileUpdateRequest(domain_tags=["Python", "FastAPI", "区块链"])

        result = await update_profile(db, user, data)

        assert result.domain_tags == ["Python", "FastAPI", "区块链"]
        db.commit.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_update_partial_fields(self):
        """部分字段更新不影响其他字段"""
        user = _make_user(nickname="原昵称", bio="原简介")
        db = _make_mock_db()
        data = ProfileUpdateRequest(bio="新简介")

        result = await update_profile(db, user, data)

        assert result.nickname == "原昵称"
        assert result.bio == "新简介"

    @pytest.mark.asyncio
    async def test_update_avatar_url(self):
        """更新头像 URL"""
        user = _make_user()
        db = _make_mock_db()
        data = ProfileUpdateRequest(avatar_url="https://example.com/avatar.jpg")

        result = await update_profile(db, user, data)

        assert result.avatar_url == "https://example.com/avatar.jpg"


# ============================================================
# 测试：头像上传
# ============================================================

class TestUploadAvatar:
    """测试 upload_avatar"""

    @pytest.mark.asyncio
    async def test_upload_avatar_with_url(self):
        """通过 URL 上传头像"""
        user = _make_user()
        db = _make_mock_db()
        data = AvatarUploadRequest(avatar_url="https://example.com/avatar.png")

        result = await upload_avatar(db, user, data)

        assert result.avatar_url == "https://example.com/avatar.png"
        assert result.avatar == "https://example.com/avatar.png"
        db.commit.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_upload_avatar_with_base64(self):
        """通过 Base64 上传头像"""
        user = _make_user()
        db = _make_mock_db()
        fake_image = base64.b64encode(b"fake_image_data").decode("ascii")
        data = AvatarUploadRequest(avatar_data=fake_image)

        result = await upload_avatar(db, user, data)

        assert result.avatar == fake_image
        assert result.avatar_url is None
        db.commit.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_upload_avatar_with_data_uri(self):
        """通过 data URI 格式上传头像"""
        user = _make_user()
        db = _make_mock_db()
        fake_image = base64.b64encode(b"fake_image_data").decode("ascii")
        data_uri = f"data:image/png;base64,{fake_image}"
        data = AvatarUploadRequest(avatar_data=data_uri)

        result = await upload_avatar(db, user, data)

        assert result.avatar == data_uri
        db.commit.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_upload_avatar_invalid_base64(self):
        """无效 Base64 数据应抛出 ValueError"""
        user = _make_user()
        db = _make_mock_db()
        data = AvatarUploadRequest(avatar_data="not_valid_base64!!!")

        with pytest.raises(ValueError, match="无效的 Base64"):
            await upload_avatar(db, user, data)


# ============================================================
# 测试：实名认证
# ============================================================

class TestVerifyIdentity:
    """测试 verify_identity"""

    @pytest.mark.asyncio
    @patch("app.modules.profile.service.encrypt_sensitive_field")
    async def test_verify_identity_success(self, mock_encrypt):
        """实名认证成功"""
        mock_encrypt.side_effect = lambda x: f"encrypted_{x}"
        user = _make_user(verified_at=None)
        db = _make_mock_db()
        data = VerifyRequest(real_name="张三", id_card="110101199001011234")

        result = await verify_identity(db, user, data)

        assert result.verified_at is not None
        assert result.real_name == "encrypted_张三"
        assert result.id_card == "encrypted_110101199001011234"
        mock_encrypt.assert_any_call("张三")
        mock_encrypt.assert_any_call("110101199001011234")
        db.commit.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_verify_identity_already_verified(self):
        """已实名认证的用户再次认证应抛出 ValueError"""
        user = _make_user(verified_at=datetime.now(timezone.utc))
        db = _make_mock_db()
        data = VerifyRequest(real_name="张三", id_card="110101199001011234")

        with pytest.raises(ValueError, match="已完成实名认证"):
            await verify_identity(db, user, data)


# ============================================================
# 测试：用户统计
# ============================================================

class TestGetUserStats:
    """测试 get_user_stats"""

    @pytest.mark.asyncio
    async def test_get_stats_basic(self):
        """获取基础统计信息"""
        now = datetime.now(timezone.utc)
        user = _make_user(credit_score=750, verified_at=now)
        db = _make_mock_db()

        stats = await get_user_stats(db, user)

        assert stats["credit_score"] == 750
        assert stats["is_verified"] is True
        assert stats["completed_tasks"] == 0
        assert stats["accepted_tasks"] == 0
        assert stats["member_since"] == user.created_at

    @pytest.mark.asyncio
    async def test_get_stats_unverified(self):
        """未实名用户的统计"""
        user = _make_user(verified_at=None)
        db = _make_mock_db()

        stats = await get_user_stats(db, user)

        assert stats["is_verified"] is False


# ============================================================
# 测试：ProfileResponse schema
# ============================================================

class TestProfileSchemas:
    """测试 Pydantic schemas"""

    def test_profile_response_from_user(self):
        """ProfileResponse 可以从 User 对象创建"""
        user = _make_user(
            nickname="测试",
            bio="简介",
            domain_tags=["Python"],
        )
        resp = user.__dict__.copy()
        # ProfileResponse 会自动过滤多余字段
        from app.schemas.user import ProfileResponse
        profile = ProfileResponse.model_validate(user)
        assert profile.nickname == "测试"
        assert profile.bio == "简介"
        assert profile.domain_tags == ["Python"]

    def test_profile_update_request_defaults(self):
        """ProfileUpdateRequest 默认所有字段为 None"""
        data = ProfileUpdateRequest()
        assert data.nickname is None
        assert data.avatar_url is None
        assert data.bio is None
        assert data.domain_tags is None

    def test_verify_request_validation(self):
        """VerifyRequest 字段验证"""
        data = VerifyRequest(real_name="张三", id_card="110101199001011234")
        assert data.real_name == "张三"
        assert data.id_card == "110101199001011234"

    def test_user_stats_response(self):
        """UserStatsResponse 构造"""
        now = datetime.now(timezone.utc)
        stats = UserStatsResponse(
            completed_tasks=5,
            accepted_tasks=10,
            credit_score=800,
            is_verified=True,
            member_since=now,
        )
        assert stats.completed_tasks == 5
        assert stats.accepted_tasks == 10
        assert stats.credit_score == 800
        assert stats.is_verified is True


# ============================================================
# 测试：路由端点（HTTP 层）
# ============================================================

class TestProfileRoutes:
    """测试 profile 路由端点"""

    @pytest.mark.asyncio
    async def test_profile_routes_registered(self):
        """profile 路由已注册到应用"""
        from httpx import ASGITransport, AsyncClient

        from app.main import app

        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            # GET /v1/users/{id}/profile 应该返回 404（用户不存在）而非 404（路由不存在）
            fake_id = str(uuid.uuid4())
            resp = await client.get(f"/v1/users/{fake_id}/profile")
            assert resp.status_code == 404
            data = resp.json()
            assert data["detail"] == "用户不存在"

            # PUT /v1/users/me/profile 应返回 401（未认证）
            resp = await client.put(
                "/v1/users/me/profile",
                json={"nickname": "test"},
            )
            assert resp.status_code == 401

            # POST /v1/users/me/avatar 应返回 401（未认证）
            resp = await client.post(
                "/v1/users/me/avatar",
                json={"avatar_url": "https://example.com/a.png"},
            )
            assert resp.status_code == 401

            # POST /v1/users/me/verify 应返回 401（未认证）
            resp = await client.post(
                "/v1/users/me/verify",
                json={"real_name": "张三", "id_card": "110101199001011234"},
            )
            assert resp.status_code == 401

            # GET /v1/users/me/stats 应返回 401（未认证）
            resp = await client.get("/v1/users/me/stats")
            assert resp.status_code == 401
