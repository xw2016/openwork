"""
安全工具模块
- JWT 生成 / 验证 (python-jose)
- 密码哈希 (passlib bcrypt)
- AES-256 敏感字段加解密 (pycryptodome)
"""

from __future__ import annotations

import base64
import hashlib
from datetime import datetime, timedelta, timezone
from typing import Any, Optional

from jose import JWTError, jwt
from passlib.context import CryptContext

from app.core.config import settings

# ============================================================
# 密码哈希
# ============================================================

pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")


def hash_password(password: str) -> str:
    """对明文密码进行 bcrypt 哈希"""
    return pwd_context.hash(password)


def verify_password(plain_password: str, hashed_password: str) -> bool:
    """验证明文密码与哈希是否匹配"""
    return pwd_context.verify(plain_password, hashed_password)


# ============================================================
# JWT 令牌
# ============================================================


def create_access_token(
    data: dict[str, Any],
    expires_delta: Optional[timedelta] = None,
) -> str:
    """
    创建 JWT access token
    :param data: 需要编码到 token 中的载荷（通常包含 sub=user_id）
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
# ============================================================

def _get_aes_key() -> bytes:
    """从配置的十六进制密钥派生 32 字节 AES 密钥"""
    return hashlib.sha256(settings.AES_SECRET_KEY.encode()).digest()


def aes_encrypt(plaintext: str) -> str:
    """
    AES-256-CBC 加密，返回 Base64 编码字符串
    使用 PKCS7 填充，随机 IV 拼接在密文前
    """
    try:
        from Crypto.Cipher import AES
        from Crypto.Util.Padding import pad
        import os
    except ImportError:
        # 如果 pycryptodome 未安装，返回原文（开发模式降级）
        return plaintext

    key = _get_aes_key()
    iv = os.urandom(16)
    cipher = AES.new(key, AES.MODE_CBC, iv)
    ct = cipher.encrypt(pad(plaintext.encode("utf-8"), AES.block_size))
    return base64.b64encode(iv + ct).decode("utf-8")


def aes_decrypt(ciphertext: str) -> str:
    """
    AES-256-CBC 解密，输入 Base64 编码字符串
    """
    try:
        from Crypto.Cipher import AES
        from Crypto.Util.Padding import unpad
    except ImportError:
        return ciphertext

    key = _get_aes_key()
    raw = base64.b64decode(ciphertext)
    iv, ct = raw[:16], raw[16:]
    cipher = AES.new(key, AES.MODE_CBC, iv)
    pt = unpad(cipher.decrypt(ct), AES.block_size)
    return pt.decode("utf-8")
