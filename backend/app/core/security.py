"""
安全工具模块
- JWT 生成 / 验证 (python-jose)
- 密码哈希 (passlib bcrypt)
- AES-256 敏感字段加解密 (pycryptodome)
"""

from __future__ import annotations

import base64
import hashlib
import warnings
from datetime import datetime, timedelta, timezone
from typing import Any, Optional

import bcrypt as _bcrypt
from jose import JWTError, jwt

from app.core.config import settings

# ============================================================
# 密码哈希 (直接使用 bcrypt，绕过 passlib 兼容性问题)
# ============================================================


def _truncate_to_72_bytes(password: str) -> bytes:
    """截断密码到 72 字节（bcrypt 限制），返回 bytes"""
    encoded = password.encode("utf-8")
    if len(encoded) <= 72:
        return encoded
    return encoded[:72]


def hash_password(password: str) -> str:
    """对明文密码进行 bcrypt 哈希（自动截断到 72 字节）"""
    return _bcrypt.hashpw(_truncate_to_72_bytes(password), _bcrypt.gensalt()).decode("utf-8")


def verify_password(plain_password: str, hashed_password: str) -> bool:
    """验证明文密码与哈希是否匹配"""
    return _bcrypt.checkpw(_truncate_to_72_bytes(plain_password), hashed_password.encode("utf-8"))


# ============================================================
# JWT 令牌
# ============================================================


def create_access_token(
    data: dict[str, Any],
    expires_delta: Optional[timedelta] = None,
) -> str:
    """
    创建 JWT access token
    :param data: 需要编码到 token 中的载荷
                  通常包含 sub=user_id, role=user_role。
                  传入 data 字典时应包含 'role' 键，例如:
                      {"sub": user_id, "role": "admin"}
    :param expires_delta: 过期时间增量，默认使用配置值
    """
    to_encode = data.copy()
    expire = datetime.now(timezone.utc) + (
        expires_delta or timedelta(minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES)
    )
    to_encode.update({"exp": expire, "type": "access"})
    return jwt.encode(to_encode, settings.SECRET_KEY, algorithm=settings.ALGORITHM)


def create_refresh_token(
    data: dict[str, Any],
    expires_delta: Optional[timedelta] = None,
) -> str:
    """创建 JWT refresh token"""
    to_encode = data.copy()
    expire = datetime.now(timezone.utc) + (
        expires_delta or timedelta(days=settings.REFRESH_TOKEN_EXPIRE_DAYS)
    )
    to_encode.update({"exp": expire, "type": "refresh"})
    return jwt.encode(to_encode, settings.SECRET_KEY, algorithm=settings.ALGORITHM)


def decode_token(token: str) -> dict[str, Any]:
    """
    解码并验证 JWT token
    :raises JWTError: token 无效或过期
    """
    return jwt.decode(token, settings.SECRET_KEY, algorithms=[settings.ALGORITHM])


# ============================================================
# AES-256 加解密 (用于 real_name / id_card 等敏感字段)
# ------------------------------------------------------------
# NOTE: aes_encrypt / aes_decrypt 使用 AES-CBC 模式，缺少完整性校验。
# 已标记为 DEPRECATED — 请迁移至 encryption.encrypt_field / decrypt_field
# （AES-GCM，带认证加密）。CBC 函数保留仅供旧数据解密使用。
# ============================================================


def _get_aes_key() -> bytes:
    """从配置的十六进制密钥派生 32 字节 AES 密钥"""
    return hashlib.sha256(settings.AES_SECRET_KEY.encode()).digest()


def aes_encrypt(plaintext: str) -> str:
    """
    DEPRECATED: AES-256-CBC 加密（无认证）。
    请迁移至 encryption.encrypt_field()（AES-GCM）。
    返回 Base64 编码字符串，随机 IV 拼接在密文前。
    """
    warnings.warn(
        "aes_encrypt uses AES-CBC without authentication and is deprecated. "
        "Use encryption.encrypt_field (AES-GCM) instead.",
        DeprecationWarning,
        stacklevel=2,
    )
    try:
        from Crypto.Cipher import AES
        from Crypto.Util.Padding import pad
        import os
    except ImportError:
        raise RuntimeError(
            "pycryptodome is required for AES encryption. "
            "Install it with: pip install pycryptodome"
        )

    key = _get_aes_key()
    iv = os.urandom(16)
    cipher = AES.new(key, AES.MODE_CBC, iv)
    ct = cipher.encrypt(pad(plaintext.encode("utf-8"), AES.block_size))
    return base64.b64encode(iv + ct).decode("utf-8")


def aes_decrypt(ciphertext: str) -> str:
    """
    DEPRECATED: AES-256-CBC 解密（无认证）。
    请迁移至 encryption.decrypt_field()（AES-GCM）。
    输入 Base64 编码字符串。
    """
    warnings.warn(
        "aes_decrypt uses AES-CBC without authentication and is deprecated. "
        "Use encryption.decrypt_field (AES-GCM) instead.",
        DeprecationWarning,
        stacklevel=2,
    )
    try:
        from Crypto.Cipher import AES
        from Crypto.Util.Padding import unpad
    except ImportError:
        raise RuntimeError(
            "pycryptodome is required for AES decryption. "
            "Install it with: pip install pycryptodome"
        )

    key = _get_aes_key()
    raw = base64.b64decode(ciphertext)
    iv, ct = raw[:16], raw[16:]
    cipher = AES.new(key, AES.MODE_CBC, iv)
    pt = unpad(cipher.decrypt(ct), AES.block_size)
    return pt.decode("utf-8")
