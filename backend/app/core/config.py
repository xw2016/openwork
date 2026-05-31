"""
OpenWork 环境变量配置
使用 pydantic-settings 从 .env / 环境变量读取配置
"""

from __future__ import annotations

import json
from typing import List

from pydantic import field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


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
    DATABASE_URL: str = "postgresql+asyncpg://openwork:openwork123@localhost:5432/openwork_db"

    # ---------- Redis ----------
    REDIS_URL: str = "redis://localhost:6379/0"

    # ---------- JWT ----------
    SECRET_KEY: str = "change-me-in-production-use-a-long-random-string"
    ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 30
    REFRESH_TOKEN_EXPIRE_DAYS: int = 7

    # ---------- AES-256 加密 ----------
    AES_SECRET_KEY: str = "change-me-aes-secret-key-32bytes!"

    # ---------- CORS ----------
    CORS_ORIGINS: List[str] = ["http://localhost:3000", "http://localhost:5173"]

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

    # ---------- 安全限流 ----------
    RATE_LIMIT_PER_MINUTE: int = 60
    RATE_LIMIT_LOGIN_PER_MINUTE: int = 5
    REQUEST_MAX_SIZE_MB: int = 10

    # ---------- 管理员初始化 ----------
    ADMIN_PHONE: str = "13800000000"
    ADMIN_PASSWORD: str = "admin123456"


settings = Settings()
