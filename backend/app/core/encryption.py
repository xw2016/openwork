"""
字段级加密工具
- AES-256-GCM 加密敏感字段（真实姓名、身份证号等）
- 支持密钥轮换（多密钥版本管理）
- 与 security.py 中的 AES-CBC 兼容并提供升级路径
"""

from __future__ import annotations

import base64
import hashlib
import json
import os
import time
from typing import Optional

import structlog

logger = structlog.get_logger("core.encryption")


# ============================================================
# 密钥管理
# ============================================================

class KeyManager:
    """
    密钥版本管理器
    支持多个密钥版本，用于密钥轮换：
    - 加密始终使用当前版本密钥
    - 解密根据密文中的版本号自动选择对应密钥
    """

    def __init__(self):
        self._keys: dict[int, bytes] = {}
        self._current_version: int = 0

    def add_key(self, version: int, key_hex: str) -> None:
        """
        添加密钥版本
        :param version: 密钥版本号（递增）
        :param key_hex: 十六进制编码的 32 字节密钥
        """
        key_bytes = bytes.fromhex(key_hex)
        if len(key_bytes) != 32:
            raise ValueError(f"密钥长度必须为 32 字节，当前 {len(key_bytes)} 字节")
        self._keys[version] = key_bytes
        if version > self._current_version:
            self._current_version = version

    def add_key_from_passphrase(self, version: int, passphrase: str) -> None:
        """从口令派生密钥"""
        key_bytes = hashlib.sha256(passphrase.encode("utf-8")).digest()
        self._keys[version] = key_bytes
        if version > self._current_version:
            self._current_version = version

    @property
    def current_version(self) -> int:
        return self._current_version

    def get_key(self, version: Optional[int] = None) -> tuple[int, bytes]:
        """获取指定版本的密钥，未指定则返回当前版本"""
        ver = version if version is not None else self._current_version
        if ver not in self._keys:
            raise ValueError(f"密钥版本 {ver} 不存在")
        return ver, self._keys[ver]


# ============================================================
# 全局密钥管理器实例
# ============================================================

_key_manager: Optional[KeyManager] = None


def get_key_manager() -> KeyManager:
    """获取全局密钥管理器"""
    global _key_manager
    if _key_manager is None:
        _key_manager = KeyManager()
    return _key_manager


def init_encryption(primary_key: str, additional_keys: Optional[dict[int, str]] = None) -> None:
    """
    初始化加密模块
    :param primary_key: 主密钥（口令形式）
    :param additional_keys: 额外的历史密钥 {版本号: 口令}，用于解密旧数据
    """
    global _key_manager
    _key_manager = KeyManager()
    _key_manager.add_key_from_passphrase(1, primary_key)
    if additional_keys:
        for version, key in additional_keys.items():
            _key_manager.add_key_from_passphrase(version, key)


# ============================================================
# AES-256-GCM 加解密
# ============================================================

def encrypt_field(plaintext: str, key_manager: Optional[KeyManager] = None) -> str:
    """
    使用 AES-256-GCM 加密敏感字段
    返回格式：base64(json({v: 密钥版本, n: nonce, t: tag, c: 密文}))
    GCM 模式提供认证加密（AEAD），同时保证机密性和完整性

    :param plaintext: 明文字符串
    :param key_manager: 密钥管理器实例
    :return: Base64 编码的加密数据
    """
    if not plaintext:
        return plaintext

    km = key_manager or get_key_manager()
    version, key = km.get_key()

    try:
        from Crypto.Cipher import AES
    except ImportError:
        raise RuntimeError("pycryptodome is required for field encryption. Install it: pip install pycryptodome")

    # 随机 12 字节 nonce（GCM 推荐）
    nonce = os.urandom(12)
    cipher = AES.new(key, AES.MODE_GCM, nonce=nonce)
    ciphertext, tag = cipher.encrypt_and_digest(plaintext.encode("utf-8"))

    # 打包加密数据
    encrypted_data = {
        "v": version,
        "n": base64.b64encode(nonce).decode("ascii"),
        "t": base64.b64encode(tag).decode("ascii"),
        "c": base64.b64encode(ciphertext).decode("ascii"),
    }
    return base64.b64encode(json.dumps(encrypted_data).encode("ascii")).decode("ascii")


def decrypt_field(encrypted_text: str, key_manager: Optional[KeyManager] = None) -> str:
    """
    解密 AES-256-GCM 加密的字段
    自动根据密文中的版本号选择对应密钥

    :param encrypted_text: Base64 编码的加密数据
    :param key_manager: 密钥管理器实例
    :return: 解密后的明文字符串
    """
    if not encrypted_text:
        return encrypted_text

    km = key_manager or get_key_manager()

    try:
        from Crypto.Cipher import AES
    except ImportError:
        raise RuntimeError("pycryptodome is required for field decryption. Install it: pip install pycryptodome")

    try:
        # 解析加密数据
        encrypted_data = json.loads(base64.b64decode(encrypted_text))
        version = encrypted_data["v"]
        nonce = base64.b64decode(encrypted_data["n"])
        tag = base64.b64decode(encrypted_data["t"])
        ciphertext = base64.b64decode(encrypted_data["c"])

        # 获取对应版本的密钥
        _, key = km.get_key(version)

        # GCM 解密 + 认证验证
        cipher = AES.new(key, AES.MODE_GCM, nonce=nonce)
        plaintext = cipher.decrypt_and_verify(ciphertext, tag)
        return plaintext.decode("utf-8")

    except (json.JSONDecodeError, KeyError, ValueError) as e:
        logger.error("decrypt_field_failed", error=str(e))
        raise ValueError(f"解密失败：数据格式错误或密钥不匹配") from e


# ============================================================
# 密钥轮换工具
# ============================================================

def rotate_encrypted_field(
    encrypted_text: str,
    old_key_manager: KeyManager,
    new_key_manager: KeyManager,
) -> str:
    """
    重新加密字段（用于密钥轮换）
    先用旧密钥解密，再用新密钥加密

    :param encrypted_text: 旧密钥加密的数据
    :param old_key_manager: 旧密钥管理器
    :param new_key_manager: 新密钥管理器
    :return: 新密钥加密的数据
    """
    plaintext = decrypt_field(encrypted_text, old_key_manager)
    return encrypt_field(plaintext, new_key_manager)


# ============================================================
# 便捷函数（兼容 security.py 中的接口）
# ============================================================

def encrypt_sensitive_field(plaintext: str) -> str:
    """加密敏感字段（真实姓名、身份证号等）"""
    return encrypt_field(plaintext)


def decrypt_sensitive_field(encrypted_text: str) -> str:
    """解密敏感字段"""
    return decrypt_field(encrypted_text)
