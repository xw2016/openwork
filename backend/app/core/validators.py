"""
输入校验与安全检测工具
- SQL 注入检测
- XSS 攻击检测
- 输入净化
- Pydantic 自定义验证器
"""

from __future__ import annotations

import re
import html
from typing import Any, Optional

import structlog
from pydantic import field_validator

logger = structlog.get_logger("core.validators")


# ============================================================
# SQL 注入检测
# ============================================================

# 常见 SQL 注入模式（正则列表，不使用内联 (?i)，改用 re.IGNORECASE 标志）
SQL_INJECTION_PATTERNS = [
    # UNION SELECT 攻击
    r"(\bunion\b.{0,100}\bselect\b)",
    # DROP TABLE / DATABASE
    r"(\bdrop\b.{0,30}\b(table|database|index|view)\b)",
    # INSERT INTO ... SELECT
    r"(\binsert\b.{0,30}\binto\b.{0,100}\bselect\b)",
    # DELETE FROM（无 WHERE 的危险删除）
    r"(\bdelete\b.{0,30}\bfrom\b)",
    # UPDATE SET（无 WHERE 的危险更新）
    r"(\bupdate\b.{0,50}\bset\b)",
    # OR 1=1 / OR '1'='1' 等永真条件
    r"(\bor\b\s+['\"]?\d+['\"]?\s*=\s*['\"]?\d+['\"]?)",
    # AND 1=1
    r"(\band\b\s+['\"]?\d+['\"]?\s*=\s*['\"]?\d+['\"]?)",
    # 单引号注入 (' OR '1'='1)
    r"('|\")\s*(or|and)\s*('|\")\s*\w+",
    # 注释符注入 (--  /*  */)
    r"(--|/\*|\*/)",
    # 分号注入（多语句执行）
    r";\s*(select|insert|update|delete|drop|alter|create|exec|execute)\b",
    # WAITFOR DELAY（时间盲注 - SQL Server）
    r"(\bwaitfor\b\s+\bdelay\b)",
    # SLEEP()（时间盲注 - MySQL）
    r"(\bsleep\s*\()",
    # BENCHMARK()（MySQL 性能攻击）
    r"(\bbenchmark\s*\()",
    # LOAD_FILE / INTO OUTFILE（MySQL 文件操作）
    r"(\b(load_file|into\s+outfile|into\s+dumpfile)\b)",
    # EXEC / EXECUTE（SQL Server 存储过程执行）
    r"(\b(exec|execute)\s*\()",
    # CHAR() / CONCAT() 绕过过滤
    r"(\b(char|concat)\s*\(\s*\d+)",
    # 16进制绕过 0x
    r"(=\s*0x[0-9a-f]+)",
    # 信息收集
    r"(\b(information_schema|sysobjects|syscolumns|pg_catalog)\b)",
]

_sql_injection_regex = re.compile("|".join(SQL_INJECTION_PATTERNS), re.IGNORECASE)


def detect_sql_injection(value: str) -> bool:
    """
    检测字符串中是否包含 SQL 注入模式
    :param value: 待检测的输入字符串
    :return: True 表示检测到可疑 SQL 注入
    """
    if not value:
        return False
    # 对 URL 编码进行解码后再检测
    try:
        from urllib.parse import unquote
        decoded = unquote(value)
    except Exception:
        decoded = value

    return bool(_sql_injection_regex.search(decoded))


def check_sql_injection(value: str, field_name: str = "input") -> None:
    """
    检测 SQL 注入，检测到则抛出 HTTP 400 异常
    """
    if detect_sql_injection(value):
        logger.warning(
            "sql_injection_detected",
            field=field_name,
            value_preview=value[:100],
        )
        from fastapi import HTTPException, status
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"输入字段 '{field_name}' 包含非法字符",
        )


# ============================================================
# XSS 攻击检测
# ============================================================

XSS_PATTERNS = [
    # script 标签
    r"<\s*script[^>]*>",
    r"<\s*/\s*script\s*>",
    # 事件处理器
    r"\bon(load|error|click|mouseover|focus|blur|submit|change|input|keydown|keyup|keypress)\s*=",
    # javascript: 协议
    r"javascript\s*:",
    # vbscript: 协议（IE）
    r"vbscript\s*:",
    # data: URI 中的 HTML/JS
    r"data\s*:\s*text/html",
    # 表达式（IE）
    r"expression\s*\(",
    # eval()
    r"eval\s*\(",
    # document.cookie / document.write
    r"document\s*\.\s*(cookie|write|location)",
    # window.location
    r"window\s*\.\s*(location|open)",
    # <iframe>, <object>, <embed>, <applet>
    r"<\s*(iframe|object|embed|applet|form|svg|math|marquee)[^>]*>",
    # src/href 中的 javascript:
    r"(src|href|action)\s*=\s*['\"]?\s*javascript:",
    # style 中的 expression
    r"style\s*=.*expression\s*\(",
    # <base> 标签
    r"<\s*base\s+",
    # <meta> 刷新跳转
    r"<\s*meta\s+.*http-equiv\s*=\s*['\"]?refresh",
]

_xss_regex = re.compile("|".join(XSS_PATTERNS), re.IGNORECASE)


def detect_xss(value: str) -> bool:
    """
    检测字符串中是否包含 XSS 攻击模式
    :param value: 待检测的输入字符串
    :return: True 表示检测到可疑 XSS
    """
    if not value:
        return False
    # HTML 解码后再检测
    decoded = html.unescape(value)
    # URL 解码
    try:
        from urllib.parse import unquote
        decoded = unquote(decoded)
    except Exception:
        pass

    return bool(_xss_regex.search(decoded))


def check_xss(value: str, field_name: str = "input") -> None:
    """
    检测 XSS，检测到则抛出 HTTP 400 异常
    """
    if detect_xss(value):
        logger.warning(
            "xss_detected",
            field=field_name,
            value_preview=value[:100],
        )
        from fastapi import HTTPException, status
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"输入字段 '{field_name}' 包含非法内容",
        )


# ============================================================
# 输入净化
# ============================================================

def sanitize_string(value: str) -> str:
    """
    净化字符串输入：
    - HTML 转义特殊字符
    - 去除前后空白
    - 去除 NULL 字节
    - 限制最大长度
    """
    if not value:
        return value
    # 去除 NULL 字节（可被用于绕过过滤）
    value = value.replace("\x00", "")
    # 去除前后空白
    value = value.strip()
    # HTML 转义
    value = html.escape(value, quote=True)
    # 限制最大长度（防止超长输入攻击）
    if len(value) > 10000:
        value = value[:10000]
    return value


def sanitize_input(data: dict[str, Any]) -> dict[str, Any]:
    """
    递归净化字典中的所有字符串值
    """
    sanitized = {}
    for key, value in data.items():
        if isinstance(value, str):
            sanitized[key] = sanitize_string(value)
        elif isinstance(value, dict):
            sanitized[key] = sanitize_input(value)
        elif isinstance(value, list):
            sanitized[key] = [
                sanitize_input(item) if isinstance(item, dict)
                else sanitize_string(item) if isinstance(item, str)
                else item
                for item in value
            ]
        else:
            sanitized[key] = value
    return sanitized


# ============================================================
# Pydantic 自定义验证器（可直接在 Schema 中使用）
# ============================================================

def safe_string_validator(*fields: str):
    """
    Pydantic 字段验证器工厂
    检测 SQL 注入 + XSS，自动净化字符串

    用法（在 Pydantic BaseModel 中）：
        _sanitize = safe_string_validator("name", "description")
    """
    @field_validator(*fields, mode="before")
    @classmethod
    def _validate(cls, v: Any) -> Any:
        if isinstance(v, str):
            # 检测 SQL 注入
            check_sql_injection(v)
            # 检测 XSS
            check_xss(v)
            # 净化输入
            return sanitize_string(v)
        return v
    return _validate


def validate_phone_number(value: str) -> str:
    """验证中国大陆手机号格式"""
    if not value:
        return value
    pattern = r"^1[3-9]\d{9}$"
    if not re.match(pattern, value):
        from fastapi import HTTPException, status
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="手机号格式不正确",
        )
    return value


def validate_email_format(value: str) -> str:
    """验证邮箱格式"""
    if not value:
        return value
    pattern = r"^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$"
    if not re.match(pattern, value):
        from fastapi import HTTPException, status
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="邮箱格式不正确",
        )
    return value


def validate_id_card(value: str) -> str:
    """验证中国大陆身份证号格式（18位）"""
    if not value:
        return value
    pattern = r"^\d{17}[\dXx]$"
    if not re.match(pattern, value):
        from fastapi import HTTPException, status
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="身份证号格式不正确",
        )
    return value
