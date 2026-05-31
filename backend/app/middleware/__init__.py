"""
安全中间件包
"""

from app.middleware.permission_middleware import PermissionMiddleware

__all__ = ["PermissionMiddleware"]
