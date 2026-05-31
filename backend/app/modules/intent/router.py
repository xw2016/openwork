"""
AI意图建模路由
- POST /analyze                  - 意图分析
- POST /blueprint                - 创建意图蓝图
- GET  /blueprint/{id}           - 获取蓝图详情
- PUT  /blueprint/{id}           - 更新蓝图
- POST /blueprint/{id}/lock      - 锁定蓝图
- GET  /blueprints               - 蓝图列表（分页）
- POST /blueprint/{id}/questions - 生成追问
- POST /question/{id}/skip       - 跳过追问
- GET  /blueprint/{id}/skip-rate - 获取跳过率
"""

from __future__ import annotations

import math
from typing import Annotated, Optional
from uuid import UUID

import structlog
from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.deps import get_current_user, get_db
from app.core.permissions import Perm
from app.models.user import User
from app.modules.intent.engine import intent_engine
from app.modules.intent.service import (
    calculate_skip_rate,
    create_blueprint,
    get_blueprint,
    get_questions_from_blueprint,
    list_blueprints,
    lock_blueprint,
    pending_clarifications,
    save_questions_to_blueprint,
    skip_question,
    update_blueprint as svc_update_blueprint,
)
from app.schemas.common import PaginatedData, ResponseBase
from app.schemas.intent import (
    BlueprintCreateRequest,
    BlueprintListResponse,
    BlueprintListItem,
    BlueprintResponse,
    BlueprintUpdateRequest,
    IntentAnalyzeRequest,
    IntentAnalyzeResponse,
    IntentAnalysisData,
    QuestionItem,
    QuestionSkipRequest,
    QuestionsResponse,
    SkipRateResponse,
)

logger = structlog.get_logger("modules.intent")

router = APIRouter(prefix="/v1/intent", tags=["AI意图建模"])


# ============================================================
# 意图分析
# ============================================================

@router.post(
    "/analyze",
    response_model=ResponseBase[IntentAnalyzeResponse],
    summary="意图分析",
)
async def analyze_intent(
    body: IntentAnalyzeRequest,
    current_user: Annotated[User, Depends(get_current_user)],
):
    """
    分析用户输入的自然语言，提取任务意图

    使用 2C1H 引擎（规则引擎模拟，不调用真实 LLM API）
    """
    analysis = intent_engine.analyze_intent(
        user_input=body.user_input,
        context=body.context,
    )

    return ResponseBase(
        message="意图分析完成",
        data=IntentAnalyzeResponse(
            analysis=IntentAnalysisData(
                task_type=analysis.task_type,
                summary=analysis.summary,
                keywords=analysis.keywords,
                confidence=analysis.confidence,
                raw_input=analysis.raw_input,
            ),
        ),
    )
analyze_intent.__permission__ = Perm.INTENT_ANALYZE


# ============================================================
# 蓝图 CRUD
# ============================================================

@router.post(
    "/blueprint",
    response_model=ResponseBase[BlueprintResponse],
    status_code=status.HTTP_201_CREATED,
    summary="创建意图蓝图",
)
async def create_intent_blueprint(
    body: BlueprintCreateRequest,
    db: Annotated[AsyncSession, Depends(get_db)],
    current_user: Annotated[User, Depends(get_current_user)],
):
    """根据用户输入创建意图蓝图"""
    blueprint = await create_blueprint(
        db=db,
        user_id=current_user.id,
        title=body.title,
        task_type=body.task_type.value,
        content=body.content,
    )

    return ResponseBase(
        code=201,
        message="蓝图创建成功",
        data=BlueprintResponse.model_validate(blueprint),
    )
create_intent_blueprint.__permission__ = Perm.INTENT_BLUEPRINT


@router.get(
    "/blueprint/{blueprint_id}",
    response_model=ResponseBase[BlueprintResponse],
    summary="获取蓝图详情",
)
async def get_intent_blueprint(
    blueprint_id: UUID,
    db: Annotated[AsyncSession, Depends(get_db)],
    current_user: Annotated[User, Depends(get_current_user)],
):
    """获取指定蓝图的详细信息"""
    blueprint = await get_blueprint(db, blueprint_id)
    if blueprint is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="蓝图不存在",
        )

    # 只有创建者可以查看
    if blueprint.user_id != current_user.id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="无权查看此蓝图",
        )

    return ResponseBase(
        data=BlueprintResponse.model_validate(blueprint),
    )
get_intent_blueprint.__permission__ = Perm.INTENT_BLUEPRINT


@router.put(
    "/blueprint/{blueprint_id}",
    response_model=ResponseBase[BlueprintResponse],
    summary="更新蓝图",
)
async def update_intent_blueprint(
    blueprint_id: UUID,
    body: BlueprintUpdateRequest,
    db: Annotated[AsyncSession, Depends(get_db)],
    current_user: Annotated[User, Depends(get_current_user)],
):
    """更新蓝图（仅 draft 状态可编辑）"""
    # 先检查蓝图存在且属于当前用户
    blueprint = await get_blueprint(db, blueprint_id)
    if blueprint is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="蓝图不存在",
        )
    if blueprint.user_id != current_user.id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="无权修改此蓝图",
        )

    try:
        updated = await svc_update_blueprint(
            db=db,
            blueprint_id=blueprint_id,
            title=body.title,
            task_type=body.task_type.value if body.task_type else None,
            content=body.content,
        )
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e),
        )

    return ResponseBase(
        message="蓝图更新成功",
        data=BlueprintResponse.model_validate(updated),
    )
update_intent_blueprint.__permission__ = Perm.INTENT_BLUEPRINT


@router.post(
    "/blueprint/{blueprint_id}/lock",
    response_model=ResponseBase[BlueprintResponse],
    summary="锁定蓝图",
)
async def lock_intent_blueprint(
    blueprint_id: UUID,
    db: Annotated[AsyncSession, Depends(get_db)],
    current_user: Annotated[User, Depends(get_current_user)],
):
    """锁定蓝图，锁定后不可再修改"""
    # 先检查蓝图存在且属于当前用户
    blueprint = await get_blueprint(db, blueprint_id)
    if blueprint is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="蓝图不存在",
        )
    if blueprint.user_id != current_user.id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="无权操作此蓝图",
        )

    try:
        locked = await lock_blueprint(db, blueprint_id)
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e),
        )

    return ResponseBase(
        message="蓝图已锁定",
        data=BlueprintResponse.model_validate(locked),
    )
lock_intent_blueprint.__permission__ = Perm.INTENT_BLUEPRINT


@router.get(
    "/blueprints",
    response_model=ResponseBase[BlueprintListResponse],
    summary="蓝图列表",
)
async def list_intent_blueprints(
    db: Annotated[AsyncSession, Depends(get_db)],
    current_user: Annotated[User, Depends(get_current_user)],
    status_filter: Optional[str] = Query(None, alias="status", description="状态过滤"),
    page: int = Query(1, ge=1, description="页码"),
    page_size: int = Query(20, ge=1, le=100, description="每页条数"),
):
    """获取当前用户的蓝图列表（分页）"""
    blueprints, total = await list_blueprints(
        db=db,
        user_id=current_user.id,
        status=status_filter,
        page=page,
        size=page_size,
    )

    items = [BlueprintListItem.model_validate(b) for b in blueprints]
    total_pages = math.ceil(total / page_size) if total > 0 else 0

    return ResponseBase(
        data=BlueprintListResponse(
            items=items,
            total=total,
            page=page,
            page_size=page_size,
            total_pages=total_pages,
        ),
    )
list_intent_blueprints.__permission__ = Perm.INTENT_BLUEPRINT


# ============================================================
# 追问管理
# ============================================================

@router.post(
    "/blueprint/{blueprint_id}/questions",
    response_model=ResponseBase[QuestionsResponse],
    summary="生成追问",
)
async def generate_questions(
    blueprint_id: UUID,
    db: Annotated[AsyncSession, Depends(get_db)],
    current_user: Annotated[User, Depends(get_current_user)],
):
    """
    根据蓝图生成追问列表

    追问分级：required（必答）、important（重要）、optional（可选）
    """
    blueprint = await get_blueprint(db, blueprint_id)
    if blueprint is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="蓝图不存在",
        )
    if blueprint.user_id != current_user.id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="无权操作此蓝图",
        )

    # 生成追问（将蓝图的 task_type 注入 content 供引擎使用）
    content_for_engine = dict(blueprint.content)
    content_for_engine.setdefault("task_type", blueprint.task_type)
    questions = intent_engine.generate_questions(content_for_engine)

    # 保存追问到蓝图 content
    await save_questions_to_blueprint(db, blueprint_id, questions)

    # 构建响应
    question_items = [
        QuestionItem(
            id=q.id,
            text=q.text,
            priority=q.priority,
            skipped=q.skipped,
            skip_reason=q.skip_reason,
        )
        for q in questions
    ]

    required_count = sum(1 for q in questions if q.priority == "required")

    return ResponseBase(
        message="追问生成成功",
        data=QuestionsResponse(
            blueprint_id=blueprint_id,
            questions=question_items,
            total=len(question_items),
            required_count=required_count,
            skipped_count=0,
        ),
    )
generate_questions.__permission__ = Perm.INTENT_BLUEPRINT


@router.post(
    "/question/{question_id}/skip",
    response_model=ResponseBase[dict],
    summary="跳过追问",
)
async def skip_question_endpoint(
    question_id: str,
    body: QuestionSkipRequest,
    db: Annotated[AsyncSession, Depends(get_db)],
    current_user: Annotated[User, Depends(get_current_user)],
):
    """跳过指定追问并记录跳过原因"""
    result = await skip_question(db, question_id, body.reason)
    if result is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="追问不存在",
        )

    return ResponseBase(
        message="追问已跳过",
        data={
            "question_id": question_id,
            "skipped": True,
            "skip_reason": body.reason,
        },
    )
skip_question_endpoint.__permission__ = Perm.INTENT_BLUEPRINT


@router.get(
    "/blueprint/{blueprint_id}/skip-rate",
    response_model=ResponseBase[SkipRateResponse],
    summary="获取跳过率",
)
async def get_skip_rate(
    blueprint_id: UUID,
    db: Annotated[AsyncSession, Depends(get_db)],
    current_user: Annotated[User, Depends(get_current_user)],
):
    """
    获取蓝图追问的跳过率

    超过30%需要警告
    """
    blueprint = await get_blueprint(db, blueprint_id)
    if blueprint is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="蓝图不存在",
        )
    if blueprint.user_id != current_user.id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="无权查看此蓝图",
        )

    total, skipped, rate = await calculate_skip_rate(db, blueprint_id)
    warning = rate > 0.3

    if warning:
        logger.warning(
            "high_skip_rate",
            blueprint_id=str(blueprint_id),
            skip_rate=rate,
        )

    return ResponseBase(
        data=SkipRateResponse(
            blueprint_id=blueprint_id,
            total_questions=total,
            skipped_questions=skipped,
            skip_rate=rate,
            warning=warning,
        ),
    )
get_skip_rate.__permission__ = Perm.INTENT_BLUEPRINT
