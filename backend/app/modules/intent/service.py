"""
意图蓝图业务逻辑
CRUD 操作 + 追问管理
"""

from __future__ import annotations

import math
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Tuple
from uuid import UUID

import structlog
from sqlalchemy import func, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.intent_blueprint import BlueprintStatus, IntentBlueprint
from app.modules.intent.engine import (
    Question,
    calculate_skip_rate_from_list,
    get_pending_questions,
    skip_question_in_list,
)

logger = structlog.get_logger("modules.intent.service")


# ============================================================
# 蓝图 CRUD
# ============================================================

async def create_blueprint(
    db: AsyncSession,
    user_id: UUID,
    title: str,
    task_type: str,
    content: Dict[str, Any],
) -> IntentBlueprint:
    """
    创建意图蓝图

    :param db: 数据库 session
    :param user_id: 用户ID
    :param title: 蓝图标题
    :param task_type: 任务类型
    :param content: 蓝图内容
    :return: 创建的蓝图对象
    """
    blueprint = IntentBlueprint(
        user_id=user_id,
        title=title,
        task_type=task_type,
        content=content,
        status=BlueprintStatus.DRAFT,
        version=1,
    )
    db.add(blueprint)
    await db.commit()
    await db.refresh(blueprint)

    logger.info(
        "blueprint_created",
        blueprint_id=str(blueprint.id),
        user_id=str(user_id),
        task_type=task_type,
    )
    return blueprint


async def get_blueprint(
    db: AsyncSession,
    blueprint_id: UUID,
) -> Optional[IntentBlueprint]:
    """
    获取蓝图详情

    :param db: 数据库 session
    :param blueprint_id: 蓝图ID
    :return: 蓝图对象，不存在返回 None
    """
    result = await db.execute(
        select(IntentBlueprint).where(IntentBlueprint.id == blueprint_id)
    )
    return result.scalar_one_or_none()


async def update_blueprint(
    db: AsyncSession,
    blueprint_id: UUID,
    title: Optional[str] = None,
    task_type: Optional[str] = None,
    content: Optional[Dict[str, Any]] = None,
) -> IntentBlueprint:
    """
    更新蓝图（仅 draft 状态可编辑）

    :param db: 数据库 session
    :param blueprint_id: 蓝图ID
    :param title: 新标题（可选）
    :param task_type: 新任务类型（可选）
    :param content: 新内容（可选）
    :return: 更新后的蓝图对象
    :raises ValueError: 蓝图不存在或状态不允许编辑
    """
    blueprint = await get_blueprint(db, blueprint_id)
    if blueprint is None:
        raise ValueError("蓝图不存在")

    if blueprint.status != BlueprintStatus.DRAFT:
        raise ValueError(
            f"蓝图当前状态为 {blueprint.status.value}，仅 draft 状态可编辑"
        )

    if title is not None:
        blueprint.title = title
    if task_type is not None:
        blueprint.task_type = task_type
    if content is not None:
        blueprint.content = content

    blueprint.version += 1
    await db.commit()
    await db.refresh(blueprint)

    logger.info(
        "blueprint_updated",
        blueprint_id=str(blueprint_id),
        version=blueprint.version,
    )
    return blueprint


async def lock_blueprint(
    db: AsyncSession,
    blueprint_id: UUID,
) -> IntentBlueprint:
    """
    锁定蓝图（不可再修改）

    :param db: 数据库 session
    :param blueprint_id: 蓝图ID
    :return: 锁定后的蓝图对象
    :raises ValueError: 蓝图不存在或状态不允许锁定
    """
    blueprint = await get_blueprint(db, blueprint_id)
    if blueprint is None:
        raise ValueError("蓝图不存在")

    if blueprint.status != BlueprintStatus.DRAFT:
        raise ValueError(
            f"蓝图当前状态为 {blueprint.status.value}，仅 draft 状态可锁定"
        )

    blueprint.status = BlueprintStatus.LOCKED
    blueprint.locked_at = datetime.now(timezone.utc)
    await db.commit()
    await db.refresh(blueprint)

    logger.info("blueprint_locked", blueprint_id=str(blueprint_id))
    return blueprint


async def list_blueprints(
    db: AsyncSession,
    user_id: UUID,
    status: Optional[str] = None,
    page: int = 1,
    size: int = 20,
) -> Tuple[List[IntentBlueprint], int]:
    """
    分页获取蓝图列表

    :param db: 数据库 session
    :param user_id: 用户ID
    :param status: 过滤状态（可选）
    :param page: 页码（从1开始）
    :param size: 每页条数
    :return: (蓝图列表, 总数)
    """
    query = select(IntentBlueprint).where(IntentBlueprint.user_id == user_id)

    if status:
        try:
            status_enum = BlueprintStatus(status)
            query = query.where(IntentBlueprint.status == status_enum)
        except ValueError:
            pass  # 忽略无效的状态值

    # 查询总数
    count_query = select(func.count()).select_from(query.subquery())
    total_result = await db.execute(count_query)
    total = total_result.scalar() or 0

    # 分页查询
    offset = (page - 1) * size
    query = query.order_by(IntentBlueprint.created_at.desc())
    query = query.offset(offset).limit(size)

    result = await db.execute(query)
    blueprints = list(result.scalars().all())

    logger.info(
        "blueprints_listed",
        user_id=str(user_id),
        total=total,
        page=page,
        size=size,
    )
    return blueprints, total


# ============================================================
# 追问管理（存储在蓝图 content.questions 字段中）
# ============================================================

async def save_questions_to_blueprint(
    db: AsyncSession,
    blueprint_id: UUID,
    questions: List[Question],
) -> IntentBlueprint:
    """
    将追问列表保存到蓝图 content 中

    :param db: 数据库 session
    :param blueprint_id: 蓝图ID
    :param questions: 追问列表
    :return: 更新后的蓝图
    """
    blueprint = await get_blueprint(db, blueprint_id)
    if blueprint is None:
        raise ValueError("蓝图不存在")

    questions_data = [
        {
            "id": q.id,
            "text": q.text,
            "priority": q.priority,
            "skipped": q.skipped,
            "skip_reason": q.skip_reason,
        }
        for q in questions
    ]

    content = dict(blueprint.content)
    content["questions"] = questions_data
    blueprint.content = content

    await db.commit()
    await db.refresh(blueprint)
    return blueprint


async def get_questions_from_blueprint(
    db: AsyncSession,
    blueprint_id: UUID,
) -> List[Dict[str, Any]]:
    """
    从蓝图 content 中获取追问列表

    :param db: 数据库 session
    :param blueprint_id: 蓝图ID
    :return: 追问列表
    :raises ValueError: 蓝图不存在
    """
    blueprint = await get_blueprint(db, blueprint_id)
    if blueprint is None:
        raise ValueError("蓝图不存在")

    # 强制刷新以获取最新的 JSONB 数据
    await db.refresh(blueprint)
    return blueprint.content.get("questions", [])


async def skip_question(
    db: AsyncSession,
    question_id: str,
    reason: str,
) -> Optional[Dict[str, Any]]:
    """
    跳过追问

    遍历所有蓝图的追问列表，找到匹配的 question_id 并标记跳过。
    （实际生产中可维护 question_id -> blueprint_id 的索引）

    :param db: 数据库 session
    :param question_id: 追问ID
    :param reason: 跳过原因
    :return: 被跳过的追问，未找到返回 None
    """
    # 查询所有蓝图（含追问的）
    result = await db.execute(
        select(IntentBlueprint).where(
            IntentBlueprint.content["questions"].astext.isnot(None)
        )
    )
    blueprints = list(result.scalars().all())

    for blueprint in blueprints:
        questions = blueprint.content.get("questions", [])
        skipped = skip_question_in_list(questions, question_id, reason)
        if skipped is not None:
            content = dict(blueprint.content)
            content["questions"] = questions
            blueprint.content = content
            await db.commit()

            logger.info(
                "question_skipped_in_db",
                question_id=question_id,
                blueprint_id=str(blueprint.id),
            )
            return skipped

    return None


async def calculate_skip_rate(
    db: AsyncSession,
    blueprint_id: UUID,
) -> Tuple[int, int, float]:
    """
    计算蓝图追问跳过率

    :param db: 数据库 session
    :param blueprint_id: 蓝图ID
    :return: (总追问数, 已跳过数, 跳过率)
    :raises ValueError: 蓝图不存在
    """
    blueprint = await get_blueprint(db, blueprint_id)
    if blueprint is None:
        raise ValueError("蓝图不存在")

    # 强制刷新以获取最新的 JSONB 数据（避免 SQLAlchemy 缓存）
    await db.refresh(blueprint)
    questions = blueprint.content.get("questions", [])
    total = len(questions)
    skipped = sum(1 for q in questions if q.get("skipped", False))
    rate = calculate_skip_rate_from_list(questions)

    return total, skipped, rate


async def pending_clarifications(
    db: AsyncSession,
    blueprint_id: UUID,
) -> List[Dict[str, Any]]:
    """
    获取待澄清项

    :param db: 数据库 session
    :param blueprint_id: 蓝图ID
    :return: 待澄清追问列表
    :raises ValueError: 蓝图不存在
    """
    questions = await get_questions_from_blueprint(db, blueprint_id)
    return get_pending_questions(questions)
