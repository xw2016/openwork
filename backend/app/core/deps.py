"""
依赖注入模块
- get_db(): 异步数据库 session
- get_current_user(): 从 JWT 解析当前用户
- require_role(): 角色权限检查（支持多角色组合）
- require_ownership(): 资源所有权检查（用户只能操作自己的数据）
"""

from __future__ import annotations

from typing import Annotated, Callable, List, Optional
from uuid import UUID

import structlog
from fastapi import Depends, HTTPException, Request, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import async_session_factory
from app.core.security import decode_token
from app.models.user import User, UserStatus, UserType

logger = structlog.get_logger("core.deps")

# HTTP Bearer scheme（自动在 Swagger UI 中添加 Authorize 按钮）
bearer_scheme = HTTPBearer()


async def get_db() -> AsyncSession:  # type: ignore[misc]
    """获取异步数据库 session，请求结束后自动关闭"""
    async with async_session_factory() as session:
        try:
            yield session
        finally:
            await session.close()


async def get_current_user(
    credentials: Annotated[HTTPAuthorizationCredentials, Depends(bearer_scheme)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> User:
    """
    从 Authorization header 中的 Bearer token 解析当前用户
    """
    credentials_exception = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="无效的认证凭据",
        headers={"WWW-Authenticate": "Bearer"},
    )
    try:
        payload = decode_token(credentials.credentials)
        user_id_str: str | None = payload.get("sub")
        token_type: str | None = payload.get("type")
        if user_id_str is None or token_type != "access":
            raise credentials_exception
        user_id = UUID(user_id_str)
    except Exception:
        raise credentials_exception

    result = await db.execute(select(User).where(User.id == user_id))
    user = result.scalar_one_or_none()
    if user is None:
        raise credentials_exception
    if user.status != UserStatus.ACTIVE:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="用户账户已被禁用",
        )
    return user


def require_role(allowed_roles: List[UserType]):
    """
    角色权限检查依赖工厂
    用法: current_user: User = Depends(require_role([UserType.ADMIN]))
    """

    async def _check_role(
        current_user: Annotated[User, Depends(get_current_user)],
    ) -> User:
        if current_user.user_type not in allowed_roles:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="权限不足，无法执行此操作",
            )
        return current_user

    return _check_role


def require_any_role(*roles: UserType):
    """
    多角色组合检查（任意一个角色即可通过）

    用法: current_user: User = Depends(require_any_role(UserType.ADMIN, UserType.EMPLOYER))
    注意：与 require_role 的区别在于参数方式更灵活，可直接传多个参数
    """

    async def _check_role(
        current_user: Annotated[User, Depends(get_current_user)],
    ) -> User:
        if current_user.user_type not in roles:
            logger.warning(
                "role_check_failed",
                user_id=str(current_user.id),
                user_type=current_user.user_type.value,
                required_roles=[r.value for r in roles],
            )
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="权限不足，无法执行此操作",
            )
        return current_user

    return _check_role


def require_all_roles(*roles: UserType):
    """
    要求用户同时具有所有指定角色
    注意：当前用户模型是单角色，此函数为未来多角色扩展预留
    """

    async def _check_role(
        current_user: Annotated[User, Depends(get_current_user)],
    ) -> User:
        # 当前为单角色模型，只检查唯一角色是否在允许列表中
        # 未来如扩展为多角色字段，可改为集合包含检查
        if current_user.user_type not in roles:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="权限不足，需要所有指定角色",
            )
        return current_user

    return _check_role


def require_admin():
    """
    管理员权限快捷依赖
    用法: current_user: User = Depends(require_admin())
    """
    return require_role([UserType.ADMIN])


def require_active_user(
    current_user: Annotated[User, Depends(get_current_user)],
) -> User:
    """
    要求用户为活跃状态（非禁用、非待审核）
    get_current_user 已包含 ACTIVE 检查，此依赖作为显式语义标记
    """
    return current_user


# ============================================================
# 资源所有权检查
# ============================================================

class OwnershipChecker:
    """
    资源所有权检查器
    确保当前用户只能操作自己的数据，管理员除外

    用法：
        @router.put("/users/{user_id}/profile")
        async def update_profile(
            user_id: UUID,
            current_user: User = Depends(OwnershipChecker("user_id")),
        ):
            # 只有资源所有者或管理员才能到达这里
            ...
    """

    def __init__(
        self,
        owner_id_param: str = "user_id",
        allow_admin: bool = True,
        owner_field: str = "id",
    ):
        """
        :param owner_id_param: 路径参数中资源所有者 ID 的参数名
        :param allow_admin: 是否允许管理员绕过所有权检查
        :param owner_field: 用户模型中用于比较的字段（默认 id）
        """
        self.owner_id_param = owner_id_param
        self.allow_admin = allow_admin
        self.owner_field = owner_field

    async def __call__(
        self,
        request: Request,
        current_user: Annotated[User, Depends(get_current_user)],
    ) -> User:
        # 管理员可绕过所有权检查
        if self.allow_admin and current_user.user_type == UserType.ADMIN:
            return current_user

        # 从路径参数获取资源所有者 ID
        owner_id_str = request.path_params.get(self.owner_id_param)
        if owner_id_str is None:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"缺少路径参数 {self.owner_id_param}",
            )

        try:
            owner_id = UUID(str(owner_id_str))
        except ValueError:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"无效的 ID 格式",
            )

        # 比较当前用户 ID 与资源所有者 ID
        user_id = getattr(current_user, self.owner_field, None)
        if user_id is None or UUID(str(user_id)) != owner_id:
            logger.warning(
                "ownership_check_failed",
                user_id=str(current_user.id),
                requested_owner=str(owner_id),
                path=str(request.url.path),
            )
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="无权操作此资源",
            )

        return current_user


def require_owner(
    owner_id_param: str = "user_id",
    allow_admin: bool = True,
):
    """
    资源所有权检查快捷函数

    用法：
        @router.delete("/contracts/{contract_id}")
        async def delete_contract(
            contract_id: UUID,
            db: AsyncSession = Depends(get_db),
            current_user: User = Depends(require_owner("user_id")),
        ):
            ...

    注意：此函数要求路径参数中包含资源所有者的 user_id
    对于更复杂的场景（如通过数据库查询资源所有者），请使用 require_ownership_checker
    """
    return OwnershipChecker(owner_id_param=owner_id_param, allow_admin=allow_admin)


async def require_ownership_checker(
    request: Request,
    current_user: Annotated[User, Depends(get_current_user)],
    resource_owner_id: UUID,
    allow_admin: bool = True,
) -> User:
    """
    通用资源所有权检查（需要提前查询资源所有者）

    用法：
        async def get_contract_owner(contract_id: UUID, db: AsyncSession) -> UUID:
            result = await db.execute(select(Contract).where(Contract.id == contract_id))
            contract = result.scalar_one_or_none()
            if not contract:
                raise HTTPException(status_code=404, detail="合同不存在")
            return contract.employer_id

        @router.put("/contracts/{contract_id}")
        async def update_contract(
            contract_id: UUID,
            db: AsyncSession = Depends(get_db),
            current_user: User = Depends(get_current_user),
        ):
            owner_id = await get_contract_owner(contract_id, db)
            await require_ownership_checker(request, current_user, owner_id)
            ...
    """
    if allow_admin and current_user.user_type == UserType.ADMIN:
        return current_user

    if current_user.id != resource_owner_id:
        logger.warning(
            "ownership_check_failed",
            user_id=str(current_user.id),
            resource_owner=str(resource_owner_id),
        )
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="无权操作此资源",
        )
    return current_user
