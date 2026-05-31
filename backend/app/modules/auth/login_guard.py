"""
登录安全防护模块
- 登录失败次数限制（同一手机号/邮箱5次失败后锁定15分钟）
- 登录日志记录（记录登录时间、IP、设备信息）
- 使用内存存储（可扩展为 Redis）
"""

from __future__ import annotations

import time
from collections import defaultdict, deque
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Optional

import structlog

logger = structlog.get_logger("auth.login_guard")

# ============================================================
# 配置常量
# ============================================================

# 最大失败次数
MAX_LOGIN_FAILURES = 5

# 锁定时间（秒）
LOCK_DURATION_SECONDS = 15 * 60  # 15分钟

# 失败记录保留时间（秒），用于过期清理
FAILURE_RECORD_TTL = 60 * 60  # 1小时


@dataclass
class LoginAttempt:
    """单次登录尝试记录"""
    timestamp: float
    ip: str
    user_agent: str
    success: bool
    failure_reason: Optional[str] = None


@dataclass
class AccountLockInfo:
    """账户锁定信息"""
    failure_count: int = 0
    lock_until: float = 0.0
    attempts: list = field(default_factory=list)


class LoginGuard:
    """
    登录安全防护器
    - 跟踪每个手机号/邮箱的登录失败次数
    - 超过阈值后锁定账户指定时间
    - 记录所有登录日志
    """

    def __init__(self):
        # 键: 手机号或邮箱, 值: AccountLockInfo
        self._lock_store: dict[str, AccountLockInfo] = defaultdict(AccountLockInfo)
        # 登录日志列表（bounded deque to prevent unbounded memory growth）
        # NOTE: For production, consider migrating to Redis for persistence
        # and shared state across multiple worker processes.
        self._login_logs: deque[dict] = deque(maxlen=10000)
        self._cleanup_counter: int = 0

    def _maybe_cleanup_stale_entries(self) -> None:
        """Periodically remove stale lock_store entries to prevent memory leak.

        Called every 100 operations (approx). Removes entries where the lock
        has expired AND all failure attempts are older than FAILURE_RECORD_TTL.
        """
        self._cleanup_counter += 1
        if self._cleanup_counter < 100:
            return
        self._cleanup_counter = 0

        now = time.time()
        stale_keys: list[str] = []
        for key, info in self._lock_store.items():
            # Only consider entries that are not currently locked
            if info.lock_until > now:
                continue
            # If all attempts are expired (or there are none), mark for cleanup
            if not info.attempts or all(
                now - a.timestamp >= FAILURE_RECORD_TTL for a in info.attempts
            ):
                stale_keys.append(key)

        for key in stale_keys:
            del self._lock_store[key]

        if stale_keys:
            logger.info("stale_lock_entries_cleaned", count=len(stale_keys))

    def _get_lock_key(self, phone: Optional[str], email: Optional[str]) -> str:
        """生成锁定键（优先使用手机号）"""
        if phone:
            return f"phone:{phone}"
        if email:
            return f"email:{email.lower()}"
        return "unknown"

    def is_locked(self, phone: Optional[str] = None, email: Optional[str] = None) -> tuple[bool, int]:
        """
        检查账户是否被锁定
        :return: (是否锁定, 剩余锁定秒数)
        """
        key = self._get_lock_key(phone, email)
        info = self._lock_store.get(key)
        if info is None:
            return False, 0

        now = time.time()

        # 检查是否在锁定期内
        if info.lock_until > now:
            remaining = int(info.lock_until - now)
            return True, remaining

        # 锁定已过期，重置失败计数
        if info.failure_count >= MAX_LOGIN_FAILURES and info.lock_until <= now:
            info.failure_count = 0
            info.lock_until = 0.0

        return False, 0

    def record_failure(
        self,
        phone: Optional[str] = None,
        email: Optional[str] = None,
        ip: str = "unknown",
        user_agent: str = "unknown",
        failure_reason: str = "用户名或密码错误",
    ) -> tuple[bool, int]:
        """
        记录一次登录失败
        :return: (是否已触发锁定, 当前失败次数)
        """
        key = self._get_lock_key(phone, email)
        info = self._lock_store[key]
        now = time.time()

        self._maybe_cleanup_stale_entries()

        # 清理过期的失败记录
        info.attempts = [a for a in info.attempts if now - a.timestamp < FAILURE_RECORD_TTL]

        # 记录本次失败
        info.failure_count += 1
        info.attempts.append(LoginAttempt(
            timestamp=now,
            ip=ip,
            user_agent=user_agent,
            success=False,
            failure_reason=failure_reason,
        ))

        # 记录日志
        self._login_logs.append({
            "login_type": "phone" if phone else "email",
            "identifier": phone or email or "unknown",
            "ip": ip,
            "user_agent": user_agent,
            "success": False,
            "failure_reason": failure_reason,
            "login_time": datetime.now(timezone.utc).isoformat(),
        })

        # 检查是否需要锁定
        if info.failure_count >= MAX_LOGIN_FAILURES:
            info.lock_until = now + LOCK_DURATION_SECONDS
            logger.warning(
                "account_locked",
                key=key,
                failure_count=info.failure_count,
                lock_seconds=LOCK_DURATION_SECONDS,
                ip=ip,
            )
            return True, info.failure_count

        logger.info(
            "login_failure_recorded",
            key=key,
            failure_count=info.failure_count,
            max_failures=MAX_LOGIN_FAILURES,
            ip=ip,
        )
        return False, info.failure_count

    def record_success(
        self,
        user_id: str,
        phone: Optional[str] = None,
        email: Optional[str] = None,
        ip: str = "unknown",
        user_agent: str = "unknown",
    ) -> None:
        """
        记录登录成功，清除失败计数
        """
        key = self._get_lock_key(phone, email)

        self._maybe_cleanup_stale_entries()

        # 清除该账户的失败记录
        if key in self._lock_store:
            self._lock_store[key] = AccountLockInfo()

        # 记录成功日志
        self._login_logs.append({
            "user_id": user_id,
            "login_type": "phone" if phone else "email",
            "identifier": phone or email or "unknown",
            "ip": ip,
            "user_agent": user_agent,
            "success": True,
            "failure_reason": None,
            "login_time": datetime.now(timezone.utc).isoformat(),
        })

        logger.info(
            "login_success_recorded",
            user_id=user_id,
            key=key,
            ip=ip,
        )

    def get_remaining_attempts(
        self,
        phone: Optional[str] = None,
        email: Optional[str] = None,
    ) -> int:
        """获取剩余登录尝试次数"""
        key = self._get_lock_key(phone, email)
        info = self._lock_store.get(key)
        if info is None:
            return MAX_LOGIN_FAILURES

        now = time.time()
        # 如果已锁定，返回0
        if info.lock_until > now:
            return 0

        # 锁定已过期
        if info.failure_count >= MAX_LOGIN_FAILURES:
            return MAX_LOGIN_FAILURES

        return max(0, MAX_LOGIN_FAILURES - info.failure_count)

    def get_login_logs(self, limit: int = 100) -> list[dict]:
        """获取最近的登录日志"""
        return self._login_logs[-limit:]

    def clear_account(self, phone: Optional[str] = None, email: Optional[str] = None) -> None:
        """清除指定账户的锁定状态（管理员操作）"""
        key = self._get_lock_key(phone, email)
        if key in self._lock_store:
            del self._lock_store[key]
            logger.info("account_lock_cleared", key=key)


# ============================================================
# 全局单例
# ============================================================
login_guard = LoginGuard()
