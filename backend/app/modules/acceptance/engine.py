"""
AI 验收引擎（规则引擎模拟）

使用规则引擎模拟 AI 验收，不调用真实 LLM。
对每个交付物进行逐项检查：格式匹配、文件完整性、内容要素覆盖。
"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import List, Optional

import structlog

from app.models.deliverable import Deliverable

logger = structlog.get_logger("modules.acceptance.engine")


# ============================================================
# 验收结果数据结构
# ============================================================


class CheckItem:
    """单项检查结果"""

    def __init__(self, name: str, status: str, detail: str, required: bool = True):
        """
        :param name: 检查项名称
        :param status: "pass" 或 "fail"
        :param detail: 详细说明
        :param required: 是否为必填项（必填项失败会导致整体 rejected）
        """
        self.name = name
        self.status = status
        self.detail = detail
        self.required = required

    def to_dict(self) -> dict:
        return {
            "name": self.name,
            "status": self.status,
            "detail": self.detail,
            "required": self.required,
        }


class EvaluationResult:
    """交付物评估结果"""

    def __init__(
        self,
        deliverable_id: uuid.UUID,
        overall: str,
        items: List[CheckItem],
    ):
        """
        :param deliverable_id: 交付物 ID
        :param overall: "approved" 或 "rejected"
        :param items: 各项检查结果列表
        """
        self.deliverable_id = deliverable_id
        self.overall = overall  # "approved" / "rejected"
        self.items = items

    def to_dict(self) -> dict:
        return {
            "deliverable_id": str(self.deliverable_id),
            "overall": self.overall,
            "items": [item.to_dict() for item in self.items],
        }


# ============================================================
# 验收引擎核心类
# ============================================================


class AcceptanceEngine:
    """
    AI 验收引擎（规则引擎模拟）

    不调用真实 LLM，使用预设规则对交付物进行逐项检查：
    1. 格式匹配 - 检查文件扩展名是否符合要求格式
    2. 文件完整性 - 检查文件 URL 和哈希是否已提供
    3. 内容要素覆盖 - 检查验收标准中要求的要素是否满足
    """

    # 支持的文件格式映射（格式关键词 -> 允许的扩展名集合）
    _FORMAT_EXTENSIONS = {
        "pdf": {".pdf"},
        "docx": {".docx", ".doc"},
        "doc": {".doc", ".docx"},
        "xlsx": {".xlsx", ".xls"},
        "xls": {".xls", ".xlsx"},
        "csv": {".csv"},
        "html": {".html", ".htm"},
        "ppt": {".ppt", ".pptx"},
        "pptx": {".pptx", ".ppt"},
        "zip": {".zip", ".rar", ".7z", ".tar", ".gz"},
        "json": {".json"},
        "psd": {".psd"},
        "sketch": {".sketch"},
        "figma": {".fig"},  # Figma 文件
        "coco": {".json", ".zip"},
        "git": set(),  # Git 仓库无扩展名要求
        "txt": {".txt"},
        "md": {".md"},
    }

    def evaluate_deliverable(
        self,
        deliverable: Deliverable,
        criteria: Optional[dict] = None,
    ) -> EvaluationResult:
        """
        评估单个交付物

        :param deliverable: 交付物 ORM 对象
        :param criteria: 验收标准（默认使用交付物自带的 acceptance_criteria）
        :return: EvaluationResult
        """
        if criteria is None:
            criteria = deliverable.acceptance_criteria or {}

        items: List[CheckItem] = []

        # 1. 格式匹配检查
        items.append(self._check_format(deliverable))

        # 2. 文件完整性检查
        items.append(self._check_file_url(deliverable))
        items.append(self._check_file_hash(deliverable))

        # 3. 内容要素覆盖检查
        items.extend(self._check_content_criteria(deliverable, criteria))

        # 判定整体结果：任一必填项 fail 则 rejected
        overall = "approved"
        for item in items:
            if item.required and item.status == "fail":
                overall = "rejected"
                break

        result = EvaluationResult(
            deliverable_id=deliverable.id,
            overall=overall,
            items=items,
        )

        logger.info(
            "deliverable_evaluated",
            deliverable_id=str(deliverable.id),
            deliverable_name=deliverable.name,
            overall=overall,
            checks_total=len(items),
            checks_passed=sum(1 for i in items if i.status == "pass"),
            checks_failed=sum(1 for i in items if i.status == "fail"),
        )

        return result

    def _check_format(self, deliverable: Deliverable) -> CheckItem:
        """
        检查文件格式是否匹配要求

        规则：如果指定了 required_format，检查文件 URL 的扩展名是否在允许范围内。
        """
        required_format = deliverable.required_format

        # 未指定格式要求，跳过检查（视为通过）
        if not required_format:
            return CheckItem(
                name="格式匹配",
                status="pass",
                detail="未指定格式要求，默认通过",
                required=False,
            )

        # 未上传文件，格式检查失败
        if not deliverable.file_url:
            return CheckItem(
                name="格式匹配",
                status="fail",
                detail=f"要求格式 {required_format}，但未上传文件",
                required=True,
            )

        # 解析文件扩展名
        file_ext = self._extract_extension(deliverable.file_url)

        # 解析要求格式（可能包含多种格式，如 "PDF/DOCX"）
        format_parts = [
            part.strip().lower() for part in required_format.replace("/", ",").split(",")
        ]

        # 收集所有允许的扩展名
        allowed_extensions: set[str] = set()
        for fmt in format_parts:
            # 去掉括号内的说明，如 "Git 仓库" -> "git"
            fmt_key = fmt.split()[0] if " " in fmt else fmt
            extensions = self._FORMAT_EXTENSIONS.get(fmt_key, set())
            if extensions:
                allowed_extensions.update(extensions)
            elif fmt_key in ("git", "仓库", "repo"):
                # Git 仓库类无扩展名要求，直接通过
                return CheckItem(
                    name="格式匹配",
                    status="pass",
                    detail=f"Git 仓库类型，无文件格式要求",
                    required=False,
                )

        # 如果没有找到匹配的格式规则，使用宽松匹配（只要文件存在即可）
        if not allowed_extensions:
            return CheckItem(
                name="格式匹配",
                status="pass",
                detail=f"要求格式 {required_format}，已上传文件 {deliverable.file_url}（宽松匹配）",
                required=False,
            )

        # 检查文件扩展名
        if file_ext in allowed_extensions:
            return CheckItem(
                name="格式匹配",
                status="pass",
                detail=f"文件格式 {file_ext} 符合要求 {required_format}",
                required=True,
            )
        else:
            return CheckItem(
                name="格式匹配",
                status="fail",
                detail=f"文件格式 {file_ext} 不符合要求 {required_format}，允许的格式：{sorted(allowed_extensions)}",
                required=True,
            )

    def _check_file_url(self, deliverable: Deliverable) -> CheckItem:
        """
        检查文件 URL 是否已提供（文件完整性 - URL）
        """
        if deliverable.file_url and deliverable.file_url.strip():
            return CheckItem(
                name="文件上传",
                status="pass",
                detail="文件 URL 已提供",
                required=True,
            )
        else:
            return CheckItem(
                name="文件上传",
                status="fail",
                detail="未提供文件 URL，请上传交付物文件",
                required=True,
            )

    def _check_file_hash(self, deliverable: Deliverable) -> CheckItem:
        """
        检查文件哈希是否已提供（文件完整性 - 哈希校验）
        """
        if deliverable.file_hash and deliverable.file_hash.strip():
            # 简单校验哈希格式（至少 32 位十六进制字符）
            hash_val = deliverable.file_hash.strip()
            if len(hash_val) >= 32 and all(
                c in "0123456789abcdefABCDEF" for c in hash_val
            ):
                return CheckItem(
                    name="文件哈希",
                    status="pass",
                    detail="文件哈希已提供且格式正确",
                    required=True,
                )
            else:
                return CheckItem(
                    name="文件哈希",
                    status="fail",
                    detail="文件哈希格式不正确，应为至少 32 位的十六进制字符串",
                    required=True,
                )
        else:
            return CheckItem(
                name="文件哈希",
                status="fail",
                detail="未提供文件哈希，请上传文件并计算 SHA-256 哈希",
                required=True,
            )

    def _check_content_criteria(
        self, deliverable: Deliverable, criteria: dict
    ) -> List[CheckItem]:
        """
        检查内容要素覆盖

        规则引擎模拟：根据验收标准中的描述性规则，进行关键词匹配和逻辑判断。
        """
        items: List[CheckItem] = []

        # 如果没有验收标准，跳过内容检查
        if not criteria:
            items.append(
                CheckItem(
                    name="内容要素覆盖",
                    status="pass",
                    detail="未定义验收标准，跳过内容检查",
                    required=False,
                )
            )
            return items

        # 检查 description 字段（通用描述性验收标准）
        description = criteria.get("description", "")
        if description:
            items.append(self._check_description_criteria(deliverable, description))

        # 检查 specific_requirements（具体要素列表）
        specific = criteria.get("specific_requirements", [])
        if isinstance(specific, list) and specific:
            for req in specific:
                if isinstance(req, dict):
                    name = req.get("name", "未命名要求")
                    req_desc = req.get("description", "")
                    items.append(
                        self._check_specific_requirement(deliverable, name, req_desc)
                    )
                elif isinstance(req, str):
                    items.append(
                        self._check_specific_requirement(deliverable, req, "")
                    )

        # 检查 min_length（最小字数要求）
        min_length = criteria.get("min_length")
        if min_length and isinstance(min_length, int):
            items.append(self._check_min_length(deliverable, min_length))

        # 检查 required_sections（必须包含的章节/模块）
        required_sections = criteria.get("required_sections", [])
        if isinstance(required_sections, list) and required_sections:
            items.append(
                self._check_required_sections(deliverable, required_sections)
            )

        # 检查 quality_score_threshold（质量分阈值）
        quality_threshold = criteria.get("quality_score_threshold")
        if quality_threshold and isinstance(quality_threshold, (int, float)):
            items.append(
                self._check_quality_score(deliverable, quality_threshold)
            )

        # 如果没有产生任何内容检查项，添加默认通过项
        if not items:
            items.append(
                CheckItem(
                    name="内容要素覆盖",
                    status="pass",
                    detail="验收标准无具体检查项，默认通过",
                    required=False,
                )
            )

        return items

    def _check_description_criteria(
        self, deliverable: Deliverable, description: str
    ) -> CheckItem:
        """
        基于描述性验收标准的检查（规则引擎模拟）

        模拟 AI 理解描述文本并判断交付物是否满足。
        规则引擎使用关键词匹配策略：
        - 如果描述中包含"包含"/"具有"等关键词，且文件已上传，视为通过
        - 如果描述中包含"禁止"/"不得"等关键词，视为需要人工审核
        """
        negative_keywords = ["禁止", "不得", "不可", "不应", "不能", "不允许"]
        has_negative = any(kw in description for kw in negative_keywords)

        if has_negative:
            # 含否定性要求的内容，规则引擎无法完全判断，标记为通过但需人工确认
            return CheckItem(
                name="内容要素覆盖",
                status="pass",
                detail=f"描述性要求：{description}（含限制性条款，建议人工复核）",
                required=False,
            )

        # 文件已上传，基于描述的正面检查视为通过
        if deliverable.file_url:
            return CheckItem(
                name="内容要素覆盖",
                status="pass",
                detail=f"文件已上传，满足描述性要求：{description}",
                required=True,
            )
        else:
            return CheckItem(
                name="内容要素覆盖",
                status="fail",
                detail=f"文件未上传，无法满足要求：{description}",
                required=True,
            )

    def _check_specific_requirement(
        self, deliverable: Deliverable, name: str, description: str
    ) -> CheckItem:
        """
        检查具体要素是否满足

        规则引擎模拟：已上传文件且有验收标准时，视为通过。
        """
        if deliverable.file_url:
            return CheckItem(
                name=f"要素：{name}",
                status="pass",
                detail=f"文件已上传，要素 {name} 视为满足",
                required=True,
            )
        else:
            return CheckItem(
                name=f"要素：{name}",
                status="fail",
                detail=f"文件未上传，无法验证要素 {name}",
                required=True,
            )

    def _check_min_length(
        self, deliverable: Deliverable, min_length: int
    ) -> CheckItem:
        """
        检查最小字数要求

        规则引擎模拟：无法实际解析文件内容，基于文件存在性判断。
        如果有 acceptance_result 中的历史数据可参考。
        """
        # 尝试从已有的验收结果中获取字数信息
        if deliverable.acceptance_result:
            word_count = deliverable.acceptance_result.get("word_count", 0)
            if word_count >= min_length:
                return CheckItem(
                    name="最小字数",
                    status="pass",
                    detail=f"字数 {word_count} >= 要求 {min_length}",
                    required=True,
                )

        if deliverable.file_url:
            return CheckItem(
                name="最小字数",
                status="pass",
                detail=f"文件已上传，要求最少 {min_length} 字（规则引擎无法解析文件内容，默认通过）",
                required=False,
            )
        else:
            return CheckItem(
                name="最小字数",
                status="fail",
                detail=f"文件未上传，无法验证最少 {min_length} 字的要求",
                required=True,
            )

    def _check_required_sections(
        self, deliverable: Deliverable, sections: list
    ) -> CheckItem:
        """
        检查必须包含的章节/模块

        规则引擎模拟：无法实际解析文件内容，基于文件存在性判断。
        """
        section_names = ", ".join(str(s) for s in sections)
        if deliverable.file_url:
            return CheckItem(
                name="必要章节",
                status="pass",
                detail=f"文件已上传，要求包含章节：{section_names}（规则引擎默认通过）",
                required=False,
            )
        else:
            return CheckItem(
                name="必要章节",
                status="fail",
                detail=f"文件未上传，无法验证必要章节：{section_names}",
                required=True,
            )

    def _check_quality_score(
        self, deliverable: Deliverable, threshold: float
    ) -> CheckItem:
        """
        检查质量分阈值

        规则引擎模拟：默认给予阈值以上的分数（假设通过）。
        """
        return CheckItem(
            name="质量评分",
            status="pass",
            detail=f"质量分阈值 {threshold}，规则引擎模拟评分通过",
            required=False,
        )

    @staticmethod
    def _extract_extension(file_url: str) -> str:
        """
        从文件 URL 中提取扩展名

        处理常见 URL 格式：
        - https://example.com/file.pdf -> .pdf
        - https://example.com/file.tar.gz -> .gz
        - https://example.com/file?v=1.pdf -> .pdf
        """
        # 去掉查询参数
        path = file_url.split("?")[0].split("#")[0]
        # 获取最后一个点后的内容
        if "." in path:
            ext = "." + path.rsplit(".", 1)[-1].lower()
            return ext
        return ""


# ============================================================
# 验收报告生成
# ============================================================


class AcceptanceReport:
    """验收报告"""

    def __init__(
        self,
        summary: str,
        total_checks: int,
        passed: int,
        failed: int,
        items: List[dict],
        timestamp: str,
    ):
        self.summary = summary
        self.total_checks = total_checks
        self.passed = passed
        self.failed = failed
        self.items = items
        self.timestamp = timestamp

    def to_dict(self) -> dict:
        return {
            "summary": self.summary,
            "total_checks": self.total_checks,
            "passed": self.passed,
            "failed": self.failed,
            "items": self.items,
            "timestamp": self.timestamp,
        }


def generate_report(
    deliverable: Deliverable, evaluation_result: EvaluationResult
) -> AcceptanceReport:
    """
    根据评估结果生成验收报告

    :param deliverable: 交付物 ORM 对象
    :param evaluation_result: 评估结果
    :return: AcceptanceReport
    """
    items = [item.to_dict() for item in evaluation_result.items]
    passed_count = sum(1 for item in evaluation_result.items if item.status == "pass")
    failed_count = sum(1 for item in evaluation_result.items if item.status == "fail")
    total = len(evaluation_result.items)

    # 生成摘要
    if evaluation_result.overall == "approved":
        summary = f"交付物「{deliverable.name}」验收通过，共 {total} 项检查全部通过"
    else:
        # 列出失败的检查项
        failed_names = [
            item.name
            for item in evaluation_result.items
            if item.status == "fail" and item.required
        ]
        summary = (
            f"交付物「{deliverable.name}」验收未通过，"
            f"{failed_count} 项检查失败：{'、'.join(failed_names)}"
        )

    report = AcceptanceReport(
        summary=summary,
        total_checks=total,
        passed=passed_count,
        failed=failed_count,
        items=items,
        timestamp=datetime.now(timezone.utc).isoformat(),
    )

    logger.info(
        "acceptance_report_generated",
        deliverable_id=str(deliverable.id),
        deliverable_name=deliverable.name,
        overall=evaluation_result.overall,
        total_checks=total,
        passed=passed_count,
        failed=failed_count,
    )

    return report
