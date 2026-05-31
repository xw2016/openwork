"""
OpenWork 环境变量配置
使用 pydantic-settings 从 .env / 环境变量读取配置
"""

from __future__ import annotations

import json
from typing import List

from pydantic import field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


WEAK_SECRET_VALUES = {
    "",
    "your-secret-key-here-change-in-production",
    "secret",
    "change-me",
    "changeme",
    "password",
    "123456",
}


class Settings(BaseSettings):
    """应用全局配置"""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
    )

    # ---------- 项目基础 ----------
    PROJECT_NAME: str = "OpenWork"
    VERSION: str = "1.0.0"
    DEBUG: bool = False

    # ---------- 数据库 ----------
    DATABASE_URL: str  # required – no default

    # ---------- Redis ----------
    REDIS_URL: str = "redis://localhost:6379/0"

    # ---------- CORS ----------
    CORS_ORIGINS: List[str] = ["*"]

    # ---------- 安全 ----------
    SECRET_KEY: str  # required – no default
    AES_SECRET_KEY: str  # required – no default
    ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 60
    REFRESH_TOKEN_EXPIRE_DAYS: int = 7

    # ---------- 安全限流 ----------
    RATE_LIMIT_PER_MINUTE: int = 60
    RATE_LIMIT_LOGIN_PER_MINUTE: int = 5
    REQUEST_MAX_SIZE_MB: int = 10

    # ---------- 管理员初始化 ----------
    ADMIN_PHONE: str  # required – no default
    ADMIN_PASSWORD: str  # required – no default

    @field_validator("CORS_ORIGINS", mode="before")
    @classmethod
    def parse_cors_origins(cls, v: str | List[str]) -> List[str]:
        """兼容 JSON 字符串和逗号分隔字符串"""
        if isinstance(v, str):
            try:
                return json.loads(v)
            except json.JSONDecodeError:
                return [i.strip() for i in v.split(",") if i.strip()]
        return v

    @field_validator("SECRET_KEY", mode="before")
    @classmethod
    def validate_secret_key(cls, v: str) -> str:
        if v.strip().lower() in WEAK_SECRET_VALUES:
            raise ValueError(
                "SECRET_KEY is too weak – use a long random string "
                "(e.g. `openssl rand -hex 32`)"
            )
        return v


settings = Settings()
