"""
RBAC 权限矩阵与权限检查工具

权限字符串格式: "module:action"
权限矩阵定义每个角色可访问的 API 权限集合
"""

from __future__ import annotations

from typing import Dict, List, Optional, Set

from app.models.user import UserType


# ============================================================
# 权限字符串常量
# ============================================================

class Perm:
    """权限字符串常量，格式 module:action"""

    # ---- 认证模块（共享） ----
    AUTH_REGISTER = "auth:register"
    AUTH_LOGIN = "auth:login"
    AUTH_REFRESH = "auth:refresh"
    AUTH_ME = "auth:me"
    AUTH_ME_UPDATE = "auth:me:update"
    AUTH_PERMISSIONS = "auth:permissions"

    # ---- 信用模块（共享：查看信用分；admin：查看历史） ----
    CREDIT_SCORE = "credit:score"
    CREDIT_HISTORY = "credit:history"

    # ---- 意图建模模块（employer） ----
    INTENT_ANALYZE = "intent:analyze"
    INTENT_BLUEPRINT = "intent:blueprint"

    # ---- 合约模块（employer） ----
    CONTRACT_CREATE = "contract:create"
    CONTRACT_LIST = "contract:list"
    CONTRACT_DETAIL = "contract:detail"
    CONTRACT_UPDATE = "contract:update"
    CONTRACT_CONFIRM = "contract:confirm"

    # ---- 合约模块（freelancer） ----
    CONTRACT_ACCEPT = "contract:accept"
    CONTRACT_SUBMIT = "contract:submit"

    # ---- 任务市场模块（freelancer 浏览/接单；employer 发布） ----
    MARKET_TASKS_LIST = "market:tasks:list"
    MARKET_TASKS_DETAIL = "market:tasks:detail"
    MARKET_BID = "market:bid"

    # ---- 验收模块（employer 验收；freelancer 查看结果） ----
    ACCEPTANCE_EVALUATE = "acceptance:evaluate"
    ACCEPTANCE_RECORDS_LIST = "acceptance:records:list"
    ACCEPTANCE_RECORDS_DETAIL = "acceptance:records:detail"
    ACCEPTANCE_REJECT = "acceptance:reject"
    ACCEPTANCE_RESUBMIT = "acceptance:resubmit"

    # ---- 资金模块（employer） ----
    PAYMENT_ESCROW = "payment:escrow"
    PAYMENT_RELEASE = "payment:release"
    PAYMENT_REFUND = "payment:refund"
    PAYMENT_TRANSACTIONS = "payment:transactions"

    # ---- 链上存证模块（admin 为主） ----
    BLOCKCHAIN_RECORD = "blockchain:record"
    BLOCKCHAIN_RECORDS = "blockchain:records"
    BLOCKCHAIN_VERIFY = "blockchain:verify"


# ============================================================
# 权限矩阵: role -> set of permission strings
# ============================================================

_SHARED_PERMISSIONS: Set[str] = {
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

_EMPLOYER_PERMISSIONS: Set[str] = {
    # 意图建模（发布任务）
    Perm.INTENT_ANALYZE,
    Perm.INTENT_BLUEPRINT,
    # 合约管理
    Perm.CONTRACT_CREATE,
    Perm.CONTRACT_LIST,
    Perm.CONTRACT_DETAIL,
    Perm.CONTRACT_UPDATE,
    Perm.CONTRACT_CONFIRM,
    # 验收
    Perm.ACCEPTANCE_EVALUATE,
    Perm.ACCEPTANCE_REJECT,
    # 资金
    Perm.PAYMENT_ESCROW,
    Perm.PAYMENT_RELEASE,
    Perm.PAYMENT_REFUND,
    Perm.PAYMENT_TRANSACTIONS,
}

_FREELANCER_PERMISSIONS: Set[str] = {
    # 接单
    Perm.MARKET_BID,
    # 合约接单与提交
    Perm.CONTRACT_ACCEPT,
    Perm.CONTRACT_SUBMIT,
    Perm.CONTRACT_LIST,
    Perm.CONTRACT_DETAIL,
    # 验收重提
    Perm.ACCEPTANCE_RESUBMIT,
    # 链上存证（提交交付物相关）
    Perm.BLOCKCHAIN_RECORD,
}

_ADMIN_ONLY_PERMISSIONS: Set[str] = {
    Perm.CREDIT_HISTORY,
    Perm.BLOCKCHAIN_RECORDS,
    Perm.BLOCKCHAIN_VERIFY,
}

PERMISSIONS: Dict[str, List[str]] = {
    UserType.ADMIN.value: sorted(
        _SHARED_PERMISSIONS
        | _EMPLOYER_PERMISSIONS
        | _FREELANCER_PERMISSIONS
        | _ADMIN_ONLY_PERMISSIONS
    ),
    UserType.EMPLOYER.value: sorted(
        _SHARED_PERMISSIONS | _EMPLOYER_PERMISSIONS
    ),
    UserType.FREELANCER.value: sorted(
        _SHARED_PERMISSIONS | _FREELANCER_PERMISSIONS
    ),
}


# ============================================================
# 权限检查工具函数
# ============================================================

def get_permissions_for_role(role: str) -> List[str]:
    """获取指定角色的权限列表"""
    return PERMISSIONS.get(role, [])


def get_permissions_for_user_type(user_type: UserType) -> List[str]:
    """根据 UserType 枚举获取权限列表"""
    return get_permissions_for_role(user_type.value)


def has_permission(user_type: UserType, permission: str) -> bool:
    """检查指定用户类型是否拥有某权限"""
    role_perms = PERMISSIONS.get(user_type.value, [])
    return permission in role_perms


def check_permission(user_type: UserType, permission: str) -> None:
    """
    权限检查，不通过时抛出 HTTPException

    用法（作为独立工具函数，非依赖注入）：
        check_permission(current_user.user_type, Perm.CONTRACT_CREATE)
    """
    from fastapi import HTTPException, status

    if not has_permission(user_type, permission):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=f"权限不足，需要权限: {permission}",
        )


def get_all_permissions() -> List[str]:
    """获取系统中所有已定义的权限（去重排序）"""
    all_perms: Set[str] = set()
    for perms in PERMISSIONS.values():
        all_perms.update(perms)
    return sorted(all_perms)
