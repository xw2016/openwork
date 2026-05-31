"""
RBAC 权限系统单元测试

测试内容：
1. 权限矩阵 PERMISSIONS 结构正确性
2. 权限检查工具函数
3. 权限中间件行为
4. 权限 API 端点
"""

from __future__ import annotations

import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from app.core.permissions import (
    PERMISSIONS,
    Perm,
    check_permission,
    get_all_permissions,
    get_permissions_for_role,
    get_permissions_for_user_type,
    has_permission,
)
from app.models.user import UserType


# ============================================================
# 权限矩阵结构测试
# ============================================================

class TestPermissionMatrix:
    """测试 PERMISSIONS 权限矩阵定义"""

    def test_matrix_contains_all_roles(self):
        """权限矩阵应包含所有角色"""
        assert UserType.ADMIN.value in PERMISSIONS
        assert UserType.EMPLOYER.value in PERMISSIONS
        assert UserType.FREELANCER.value in PERMISSIONS

    def test_admin_has_all_permissions(self):
        """管理员应拥有所有权限"""
        admin_perms = set(PERMISSIONS[UserType.ADMIN.value])
        all_perms = set(get_all_permissions())
        assert admin_perms == all_perms, (
            f"管理员缺少权限: {all_perms - admin_perms}"
        )

    def test_employer_has_required_permissions(self):
        """雇主应拥有创建合约、发布任务、验收等权限"""
        employer_perms = set(PERMISSIONS[UserType.EMPLOYER.value])
        required = {
            Perm.CONTRACT_CREATE,
            Perm.CONTRACT_LIST,
            Perm.CONTRACT_DETAIL,
            Perm.CONTRACT_UPDATE,
            Perm.CONTRACT_CONFIRM,
            Perm.INTENT_ANALYZE,
            Perm.INTENT_BLUEPRINT,
            Perm.ACCEPTANCE_EVALUATE,
            Perm.PAYMENT_ESCROW,
            Perm.PAYMENT_RELEASE,
            Perm.PAYMENT_REFUND,
            Perm.PAYMENT_TRANSACTIONS,
        }
        assert required.issubset(employer_perms), (
            f"雇主缺少权限: {required - employer_perms}"
        )

    def test_freelancer_has_required_permissions(self):
        """自由职业者应拥有浏览市场、接单等权限"""
        freelancer_perms = set(PERMISSIONS[UserType.FREELANCER.value])
        required = {
            Perm.MARKET_BID,
            Perm.BLOCKCHAIN_RECORD,
        }
        assert required.issubset(freelancer_perms), (
            f"自由职业者缺少权限: {required - freelancer_perms}"
        )

    def test_shared_permissions_present_for_all_roles(self):
        """共享权限应存在于所有角色中"""
        shared = {
            Perm.AUTH_REGISTER,
            Perm.AUTH_LOGIN,
            Perm.AUTH_REFRESH,
            Perm.AUTH_ME,
            Perm.AUTH_ME_UPDATE,
            Perm.AUTH_PERMISSIONS,
            Perm.CREDIT_SCORE,
            Perm.MARKET_TASKS_LIST,
            Perm.MARKET_TASKS_DETAIL,
            Perm.ACCEPTANCE_RECORDS_LIST,
            Perm.ACCEPTANCE_RECORDS_DETAIL,
        }
        for role in [UserType.ADMIN, UserType.EMPLOYER, UserType.FREELANCER]:
            role_perms = set(PERMISSIONS[role.value])
            assert shared.issubset(role_perms), (
                f"角色 {role.value} 缺少共享权限: {shared - role_perms}"
            )

    def test_permissions_are_sorted(self):
        """每个角色的权限列表应为排序状态"""
        for role, perms in PERMISSIONS.items():
            assert perms == sorted(perms), f"角色 {role} 的权限列表未排序"

    def test_no_duplicate_permissions_per_role(self):
        """每个角色的权限列表不应有重复"""
        for role, perms in PERMISSIONS.items():
            assert len(perms) == len(set(perms)), f"角色 {role} 存在重复权限"


# ============================================================
# 权限常量测试
# ============================================================

class TestPermConstants:
    """测试 Perm 权限常量"""

    def test_perm_format(self):
        """权限字符串应符合 module:action 或 module:submodule:action 格式"""
        all_attrs = [
            getattr(Perm, attr)
            for attr in dir(Perm)
            if not attr.startswith("_")
        ]
        for perm_str in all_attrs:
            assert ":" in perm_str, f"权限 {perm_str} 不符合 module:action 格式"
            parts = perm_str.split(":")
            assert len(parts) >= 2, f"权限 {perm_str} 格式不正确"
            for part in parts:
                assert part, f"权限 {perm_str} 包含空的部分"

    def test_perm_constants_are_strings(self):
        """所有权限常量应为字符串类型"""
        for attr in dir(Perm):
            if not attr.startswith("_"):
                assert isinstance(getattr(Perm, attr), str)


# ============================================================
# 权限检查工具函数测试
# ============================================================

class TestPermissionUtils:
    """测试权限检查工具函数"""

    def test_get_permissions_for_role_valid(self):
        """应能获取有效角色的权限列表"""
        perms = get_permissions_for_role("admin")
        assert isinstance(perms, list)
        assert len(perms) > 0

    def test_get_permissions_for_role_invalid(self):
        """无效角色应返回空列表"""
        perms = get_permissions_for_role("nonexistent")
        assert perms == []

    def test_get_permissions_for_user_type(self):
        """应能通过 UserType 枚举获取权限列表"""
        perms = get_permissions_for_user_type(UserType.EMPLOYER)
        assert isinstance(perms, list)
        assert Perm.CONTRACT_CREATE in perms

    def test_has_permission_true(self):
        """管理员应拥有所有权限"""
        assert has_permission(UserType.ADMIN, Perm.CONTRACT_CREATE) is True
        assert has_permission(UserType.ADMIN, Perm.MARKET_BID) is True

    def test_has_permission_employer(self):
        """雇主应拥有合约创建权限，不应拥有接单权限"""
        assert has_permission(UserType.EMPLOYER, Perm.CONTRACT_CREATE) is True
        assert has_permission(UserType.EMPLOYER, Perm.MARKET_BID) is False

    def test_has_permission_freelancer(self):
        """自由职业者应拥有接单权限，不应拥有合约创建权限"""
        assert has_permission(UserType.FREELANCER, Perm.MARKET_BID) is True
        assert has_permission(UserType.FREELANCER, Perm.CONTRACT_CREATE) is False

    def test_has_permission_shared(self):
        """共享权限应对所有角色可用"""
        for role in UserType:
            assert has_permission(role, Perm.AUTH_LOGIN) is True
            assert has_permission(role, Perm.CREDIT_SCORE) is True

    def test_check_permission_passes(self):
        """有权限时不应抛出异常"""
        # 不应抛出异常
        check_permission(UserType.ADMIN, Perm.CONTRACT_CREATE)

    def test_check_permission_raises(self):
        """无权限时应抛出 HTTPException"""
        from fastapi import HTTPException
        with pytest.raises(HTTPException) as exc_info:
            check_permission(UserType.FREELANCER, Perm.CONTRACT_CREATE)
        assert exc_info.value.status_code == 403

    def test_get_all_permissions_returns_sorted_unique(self):
        """应返回去重排序的所有权限列表"""
        all_perms = get_all_permissions()
        assert isinstance(all_perms, list)
        assert all_perms == sorted(all_perms)
        assert len(all_perms) == len(set(all_perms))

    def test_get_all_permissions_covers_matrix(self):
        """所有权限列表应覆盖权限矩阵中的所有权限"""
        all_perms = set(get_all_permissions())
        for role, perms in PERMISSIONS.items():
            for perm in perms:
                assert perm in all_perms, (
                    f"权限 {perm} 在角色 {role} 中但不在全局列表中"
                )


# ============================================================
# 权限中间件测试
# ============================================================

class TestPermissionMiddleware:
    """测试权限中间件"""

    def test_middleware_skips_public_paths(self,):
        """中间件应跳过公开路径"""
        from app.middleware.permission_middleware import _PUBLIC_PATH_PREFIXES

        assert "/health" in _PUBLIC_PATH_PREFIXES
        assert "/docs" in _PUBLIC_PATH_PREFIXES
        assert "/openapi.json" in _PUBLIC_PATH_PREFIXES
        assert "/redoc" in _PUBLIC_PATH_PREFIXES

    def test_middleware_class_exists(self):
        """PermissionMiddleware 类应存在且继承自 BaseHTTPMiddleware"""
        from starlette.middleware.base import BaseHTTPMiddleware
        from app.middleware.permission_middleware import PermissionMiddleware

        assert issubclass(PermissionMiddleware, BaseHTTPMiddleware)

    def test_middleware_has_dispatch(self):
        """PermissionMiddleware 应实现 dispatch 方法"""
        from app.middleware.permission_middleware import PermissionMiddleware

        assert hasattr(PermissionMiddleware, "dispatch")


# ============================================================
# 路由权限注解测试
# ============================================================

class TestRoutePermissions:
    """测试路由上的权限注解"""

    def test_auth_router_has_permissions(self):
        """认证路由的端点应有权限注解"""
        from app.modules.auth.router import (
            register, login, refresh_token, get_me, get_permissions,
        )
        assert getattr(register, "__permission__", None) == Perm.AUTH_REGISTER
        assert getattr(login, "__permission__", None) == Perm.AUTH_LOGIN
        assert getattr(refresh_token, "__permission__", None) == Perm.AUTH_REFRESH
        assert getattr(get_me, "__permission__", None) == Perm.AUTH_ME
        assert getattr(get_permissions, "__permission__", None) == Perm.AUTH_PERMISSIONS

    def test_contract_router_has_permissions(self):
        """合约路由的端点应有权限注解"""
        from app.modules.contract.router import (
            create_contract, list_contracts, get_contract,
            update_contract, complete_contract,
            publish_contract, accept_contract, submit_for_review,
            terminate_contract, get_deliverables, generate_deliverables,
        )
        assert getattr(create_contract, "__permission__", None) == Perm.CONTRACT_CREATE
        assert getattr(list_contracts, "__permission__", None) == Perm.CONTRACT_LIST
        assert getattr(get_contract, "__permission__", None) == Perm.CONTRACT_DETAIL
        assert getattr(update_contract, "__permission__", None) == Perm.CONTRACT_UPDATE
        assert getattr(complete_contract, "__permission__", None) == Perm.CONTRACT_CONFIRM
        # 新增端点
        assert getattr(publish_contract, "__permission__", None) == Perm.CONTRACT_UPDATE
        assert getattr(accept_contract, "__permission__", None) == Perm.CONTRACT_ACCEPT
        assert getattr(submit_for_review, "__permission__", None) == Perm.CONTRACT_SUBMIT
        assert getattr(terminate_contract, "__permission__", None) == Perm.CONTRACT_UPDATE
        assert getattr(get_deliverables, "__permission__", None) == Perm.CONTRACT_DETAIL
        assert getattr(generate_deliverables, "__permission__", None) == Perm.CONTRACT_UPDATE

    def test_market_router_has_permissions(self):
        """市场路由的端点应有权限注解"""
        from app.modules.market.router import list_tasks, get_task, bid_task
        assert getattr(list_tasks, "__permission__", None) == Perm.MARKET_TASKS_LIST
        assert getattr(get_task, "__permission__", None) == Perm.MARKET_TASKS_DETAIL
        assert getattr(bid_task, "__permission__", None) == Perm.MARKET_BID

    def test_acceptance_router_has_permissions(self):
        """验收路由的端点应有权限注解"""
        from app.modules.acceptance.router import (
            evaluate_contract, list_records, get_record,
            reject_deliverable, resubmit_deliverable,
        )
        assert getattr(evaluate_contract, "__permission__", None) == Perm.ACCEPTANCE_EVALUATE
        assert getattr(list_records, "__permission__", None) == Perm.ACCEPTANCE_RECORDS_LIST
        assert getattr(get_record, "__permission__", None) == Perm.ACCEPTANCE_RECORDS_DETAIL
        assert getattr(reject_deliverable, "__permission__", None) == Perm.ACCEPTANCE_REJECT
        assert getattr(resubmit_deliverable, "__permission__", None) == Perm.ACCEPTANCE_RESUBMIT

    def test_payment_router_has_permissions(self):
        """资金路由的端点应有权限注解"""
        from app.modules.payment.router import (
            escrow_funds, release_funds, refund, list_transactions,
        )
        assert getattr(escrow_funds, "__permission__", None) == Perm.PAYMENT_ESCROW
        assert getattr(release_funds, "__permission__", None) == Perm.PAYMENT_RELEASE
        assert getattr(refund, "__permission__", None) == Perm.PAYMENT_REFUND
        assert getattr(list_transactions, "__permission__", None) == Perm.PAYMENT_TRANSACTIONS

    def test_credit_router_has_permissions(self):
        """信用路由的端点应有权限注解"""
        from app.modules.credit.router import (
            get_my_credit_score, get_my_credit_history,
            refresh_my_credit_score, get_user_credit_score,
        )
        assert getattr(get_my_credit_score, "__permission__", None) == Perm.CREDIT_SCORE
        assert getattr(get_my_credit_history, "__permission__", None) == Perm.CREDIT_HISTORY
        assert getattr(refresh_my_credit_score, "__permission__", None) == Perm.CREDIT_SCORE
        assert getattr(get_user_credit_score, "__permission__", None) == Perm.CREDIT_SCORE

    def test_blockchain_router_has_permissions(self):
        """区块链路由的端点应有权限注解"""
        from app.modules.blockchain.router import (
            create_record, list_records_by_contract, get_record, verify_record,
        )
        assert getattr(create_record, "__permission__", None) == Perm.BLOCKCHAIN_RECORD
        assert getattr(list_records_by_contract, "__permission__", None) == Perm.BLOCKCHAIN_RECORDS
        assert getattr(get_record, "__permission__", None) == Perm.BLOCKCHAIN_RECORDS
        assert getattr(verify_record, "__permission__", None) == Perm.BLOCKCHAIN_VERIFY

    def test_intent_router_has_permissions(self):
        """意图路由的端点应有权限注解"""
        from app.modules.intent.router import analyze_intent, generate_blueprint
        assert getattr(analyze_intent, "__permission__", None) == Perm.INTENT_ANALYZE
        assert getattr(generate_blueprint, "__permission__", None) == Perm.INTENT_BLUEPRINT


# ============================================================
# 与现有 RBAC 兼容性测试
# ============================================================

class TestRBACCompatibility:
    """测试新权限系统与现有 RBAC 的兼容性"""

    def test_require_role_still_works(self):
        """require_role 应继续正常工作"""
        from app.core.deps import require_role
        dep = require_role([UserType.ADMIN])
        assert callable(dep)

    def test_require_any_role_still_works(self):
        """require_any_role 应继续正常工作"""
        from app.core.deps import require_any_role
        dep = require_any_role(UserType.ADMIN, UserType.EMPLOYER)
        assert callable(dep)

    def test_require_admin_still_works(self):
        """require_admin 应继续正常工作"""
        from app.core.deps import require_admin
        dep = require_admin()
        assert callable(dep)

    def test_ownership_checker_still_works(self):
        """OwnershipChecker 应继续正常工作"""
        from app.core.deps import OwnershipChecker
        checker = OwnershipChecker("user_id")
        assert callable(checker)

    def test_user_type_enum_unchanged(self):
        """UserType 枚举应保持不变"""
        assert UserType.EMPLOYER.value == "employer"
        assert UserType.FREELANCER.value == "freelancer"
        assert UserType.ADMIN.value == "admin"
