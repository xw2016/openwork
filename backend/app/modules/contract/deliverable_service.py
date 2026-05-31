"""
交付物清单生成与管理服务
根据任务类型和蓝图自动生成交付物清单，支持批量创建和查询
"""

from __future__ import annotations

from datetime import datetime, timezone
from decimal import Decimal
from typing import List, Optional
from uuid import UUID

import structlog
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.contract import TaskType
from app.models.deliverable import AcceptanceStatus, Deliverable

logger = structlog.get_logger("modules.contract.deliverable_service")

# ============================================================
# 各任务类型的默认交付物模板
# ============================================================

_DELIVERABLE_TEMPLATES: dict[str, List[dict]] = {
    TaskType.DEVELOPMENT: [
        {
            "name": "需求文档",
            "required_format": "PDF/DOCX",
            "acceptance_criteria": {"description": "包含完整的需求描述和验收标准"},
        },
        {
            "name": "源代码",
            "required_format": "Git 仓库",
            "acceptance_criteria": {"description": "符合编码规范，包含注释和 README"},
        },
        {
            "name": "测试报告",
            "required_format": "PDF/HTML",
            "acceptance_criteria": {"description": "包含单元测试、集成测试结果"},
        },
        {
            "name": "部署文档",
            "required_format": "PDF/DOCX",
            "acceptance_criteria": {"description": "包含部署步骤、环境配置和回滚方案"},
        },
    ],
    TaskType.DESIGN: [
        {
            "name": "设计稿",
            "required_format": "PSD/Sketch/Figma",
            "acceptance_criteria": {"description": "包含完整的视觉设计和交互说明"},
        },
        {
            "name": "标注文件",
            "required_format": "Zeplin/Sketch Measure",
            "acceptance_criteria": {"description": "包含尺寸、颜色、字体等标注信息"},
        },
        {
            "name": "素材包",
            "required_format": "ZIP",
            "acceptance_criteria": {"description": "包含切图、图标、字体等设计资源"},
        },
    ],
    TaskType.COPYWRITING: [
        {
            "name": "初稿",
            "required_format": "DOCX/PDF",
            "acceptance_criteria": {"description": "满足字数和主题要求的初版文案"},
        },
        {
            "name": "终稿",
            "required_format": "DOCX/PDF",
            "acceptance_criteria": {"description": "经过修改确认的最终版本"},
        },
        {
            "name": "修改说明",
            "required_format": "DOCX/PDF",
            "acceptance_criteria": {"description": "记录修改原因和变更内容"},
        },
    ],
    TaskType.TRANSLATION: [
        {
            "name": "译文",
            "required_format": "DOCX/PDF",
            "acceptance_criteria": {"description": "准确、流畅的翻译文本"},
        },
        {
            "name": "术语表",
            "required_format": "XLSX/CSV",
            "acceptance_criteria": {"description": "专业术语对照表"},
        },
        {
            "name": "校对记录",
            "required_format": "DOCX/PDF",
            "acceptance_criteria": {"description": "校对修改记录和注释"},
        },
    ],
    TaskType.DATA_LABELING: [
        {
            "name": "标注数据集",
            "required_format": "JSON/CSV/COCO",
            "acceptance_criteria": {"description": "符合标注规范的结构化数据"},
        },
        {
            "name": "质量报告",
            "required_format": "PDF/HTML",
            "acceptance_criteria": {"description": "包含准确率、一致性等质量指标"},
        },
    ],
    TaskType.CONSULTING: [
        {
            "name": "咨询报告",
            "required_format": "PDF/DOCX",
            "acceptance_criteria": {"description": "包含分析结论和建议的完整报告"},
        },
        {
            "name": "演示文稿",
            "required_format": "PPT/PDF",
            "acceptance_criteria": {"description": "用于汇报的演示幻灯片"},
        },
    ],
    TaskType.OTHER: [
        {
            "name": "交付物",
            "required_format": "根据具体约定",
            "acceptance_criteria": {"description": "按合约要求交付"},
        },
    ],
}


def generate_deliverables(
    task_type: str, blueprint: Optional[dict] = None
) -> List[dict]:
    """
    根据任务类型和蓝图自动生成交付物清单

    :param task_type: 任务类型（枚举值字符串）
    :param blueprint: 意图蓝图（可选，用于定制交付物）
    :return: 交付物清单列表
    """
    # 获取默认模板
    try:
        tt = TaskType(task_type)
    except ValueError:
        tt = TaskType.OTHER

    template = _DELIVERABLE_TEMPLATES.get(tt, _DELIVERABLE_TEMPLATES[TaskType.OTHER])

    # 基于蓝图定制（如果有）
    deliverables = []
    for idx, item in enumerate(template, start=1):
        deliverable = {
            "deliverable_index": idx,
            "name": item["name"],
            "required_format": item["required_format"],
            "acceptance_criteria": item["acceptance_criteria"],
        }
        deliverables.append(deliverable)

    # 蓝图可以追加额外的交付物
    if blueprint and "extra_deliverables" in blueprint:
        extra = blueprint["extra_deliverables"]
        if isinstance(extra, list):
            for idx_offset, item in enumerate(extra):
                if isinstance(item, dict) and "name" in item:
                    deliverables.append({
                        "deliverable_index": len(deliverables) + 1,
                        "name": item["name"],
                        "required_format": item.get("required_format", ""),
                        "acceptance_criteria": item.get("acceptance_criteria", {}),
                    })

    logger.info(
        "deliverables_generated",
        task_type=task_type,
        count=len(deliverables),
    )
    return deliverables


async def create_deliverables(
    db: AsyncSession,
    contract_id: UUID,
    deliverables: List[dict],
) -> List[Deliverable]:
    """
    批量创建交付物记录

    :param db: 数据库 session
    :param contract_id: 合约 ID
    :param deliverables: 交付物数据列表
    :return: 创建的 Deliverable 对象列表
    """
    records = []
    for item in deliverables:
        d = Deliverable(
            contract_id=contract_id,
            deliverable_index=item.get("deliverable_index", len(records) + 1),
            name=item["name"],
            required_format=item.get("required_format"),
            acceptance_criteria=item.get("acceptance_criteria", {}),
            acceptance_status=AcceptanceStatus.NOT_SUBMITTED,
        )
        db.add(d)
        records.append(d)

    await db.commit()
    # 刷新所有记录以获取生成的 id 等字段
    for d in records:
        await db.refresh(d)

    logger.info(
        "deliverables_created",
        contract_id=str(contract_id),
        count=len(records),
    )
    return records


async def get_deliverables(
    db: AsyncSession, contract_id: UUID
) -> List[Deliverable]:
    """
    获取合约的交付物列表

    :param db: 数据库 session
    :param contract_id: 合约 ID
    :return: 交付物列表（按 deliverable_index 排序）
    """
    result = await db.execute(
        select(Deliverable)
        .where(Deliverable.contract_id == contract_id)
        .order_by(Deliverable.deliverable_index)
    )
    return list(result.scalars().all())
