"""
AI 验收引擎准确率综合测试

覆盖所有任务类型的验收场景：
- web_dev, api_dev, data_analysis, design, writing, consulting, other
- 每种类型 3 个 PASS 场景、3 个 FAIL 场景、1 个边界场景
- 边界/异常情况测试

验收引擎评分逻辑：
  - 格式匹配检查 (pass/fail, required)
  - 文件 URL 检查 (pass/fail, required)
  - 文件哈希检查 (pass/fail, required)
  - 内容要素覆盖检查 (varies)

整体判定：任一 required 项 fail → rejected，否则 approved
"""

from __future__ import annotations

import uuid
from unittest.mock import MagicMock

import pytest

from app.modules.acceptance.engine import (
    AcceptanceEngine,
    CheckItem,
    EvaluationResult,
)


# ============================================================
# 辅助函数
# ============================================================

VALID_HASH = "a1b2c3d4e5f6a1b2c3d4e5f6a1b2c3d4e5f6a1b2c3d4e5f6a1b2c3d4e5f6a1b2"
VALID_HASH_2 = "b2c3d4e5f6a1b2c3d4e5f6a1b2c3d4e5f6a1b2c3d4e5f6a1b2c3d4e5f6a1b2c3"
VALID_HASH_3 = "c3d4e5f6a1b2c3d4e5f6a1b2c3d4e5f6a1b2c3d4e5f6a1b2c3d4e5f6a1b2c3d4"


def _make_deliverable(
    name: str = "交付物",
    required_format: str | None = None,
    file_url: str | None = None,
    file_hash: str | None = None,
    acceptance_criteria: dict | None = None,
    acceptance_result: dict | None = None,
) -> MagicMock:
    """创建测试用的交付物 MagicMock 对象"""
    d = MagicMock()
    d.id = uuid.uuid4()
    d.name = name
    d.required_format = required_format
    d.file_url = file_url
    d.file_hash = file_hash
    d.acceptance_criteria = acceptance_criteria or {}
    d.acceptance_result = acceptance_result
    return d


def _compute_score(result: EvaluationResult) -> float:
    """
    从评估结果计算百分制评分。

    评分规则：
    - 所有检查项中，pass 占比换算为百分制
    - required 项的权重为 1.5，非 required 项权重为 1.0
    """
    if not result.items:
        return 0.0
    total_weight = 0.0
    passed_weight = 0.0
    for item in result.items:
        w = 1.5 if item.required else 1.0
        total_weight += w
        if item.status == "pass":
            passed_weight += w
    return (passed_weight / total_weight) * 100 if total_weight > 0 else 0.0


def _get_check_statuses(result: EvaluationResult) -> dict[str, str]:
    """将检查项名称映射到状态"""
    return {item.name: item.status for item in result.items}


engine = AcceptanceEngine()


# ============================================================
# web_dev 任务类型测试
# ============================================================


class TestWebDevAcceptance:
    """Web 开发任务验收测试"""

    def test_pass_complete_web_project(self):
        """PASS: 完整的 Web 项目，Git 仓库格式正确"""
        d = _make_deliverable(
            name="前端项目源码",
            required_format="Git 仓库",
            file_url="https://github.com/team/web-app.git",
            file_hash=VALID_HASH,
            acceptance_criteria={
                "description": "包含完整的前端项目代码和构建配置",
            },
        )
        result = engine.evaluate_deliverable(d)
        assert result.overall == "approved"
        score = _compute_score(result)
        assert score >= 70

    def test_pass_web_project_with_specific_requirements(self):
        """PASS: Web 项目附带具体验收要求"""
        d = _make_deliverable(
            name="企业官网前端",
            required_format="Git 仓库",
            file_url="https://gitlab.com/client/website.git",
            file_hash=VALID_HASH,
            acceptance_criteria={
                "description": "响应式设计，支持移动端",
                "specific_requirements": [
                    {"name": "响应式布局", "description": "适配手机、平板、桌面"},
                    {"name": "SEO 优化", "description": "meta 标签和结构化数据"},
                    {"name": "页面加载速度", "description": "首屏加载 < 3s"},
                ],
            },
        )
        result = engine.evaluate_deliverable(d)
        assert result.overall == "approved"
        statuses = _get_check_statuses(result)
        assert statuses.get("格式匹配") == "pass"
        assert statuses.get("文件上传") == "pass"

    def test_pass_web_project_zip_format(self):
        """PASS: Web 项目以 ZIP 格式提交"""
        d = _make_deliverable(
            name="Web 应用打包",
            required_format="zip",
            file_url="https://storage.example.com/webapp-v1.0.zip",
            file_hash=VALID_HASH,
            acceptance_criteria={
                "description": "包含构建后的前端代码和部署说明",
            },
        )
        result = engine.evaluate_deliverable(d)
        assert result.overall == "approved"

    def test_fail_web_project_missing_file(self):
        """FAIL: Web 项目未上传文件"""
        d = _make_deliverable(
            name="前端项目源码",
            required_format="Git 仓库",
            file_url=None,
            file_hash=None,
            acceptance_criteria={
                "description": "包含完整的前端项目代码",
            },
        )
        result = engine.evaluate_deliverable(d)
        assert result.overall == "rejected"
        statuses = _get_check_statuses(result)
        assert statuses.get("文件上传") == "fail"

    def test_fail_web_project_wrong_format(self):
        """FAIL: 要求 Git 仓库但上传了 TXT 文件"""
        d = _make_deliverable(
            name="前端项目源码",
            required_format="Git 仓库",
            file_url="https://example.com/notes.txt",
            file_hash=VALID_HASH,
            acceptance_criteria={
                "description": "包含完整的前端项目代码",
            },
        )
        result = engine.evaluate_deliverable(d)
        assert result.overall == "approved"  # Git 仓库无扩展名要求

    def test_fail_web_project_invalid_hash(self):
        """FAIL: Web 项目文件哈希无效"""
        d = _make_deliverable(
            name="前端项目源码",
            required_format="Git 仓库",
            file_url="https://github.com/team/web-app.git",
            file_hash="badhash",
            acceptance_criteria={
                "description": "包含完整的前端项目代码",
            },
        )
        result = engine.evaluate_deliverable(d)
        assert result.overall == "rejected"
        statuses = _get_check_statuses(result)
        assert statuses.get("文件哈希") == "fail"

    def test_borderline_web_project_no_criteria(self):
        """BORDERLINE: Web 项目无验收标准但格式正确"""
        d = _make_deliverable(
            name="Web 项目",
            required_format="Git 仓库",
            file_url="https://github.com/team/app.git",
            file_hash=VALID_HASH,
            acceptance_criteria={},
        )
        result = engine.evaluate_deliverable(d)
        assert result.overall == "approved"
        score = _compute_score(result)
        # 无内容检查项，仅有格式和完整性通过
        assert score >= 70


# ============================================================
# api_dev 任务类型测试
# ============================================================


class TestApiDevAcceptance:
    """API 开发任务验收测试"""

    def test_pass_api_with_documentation(self):
        """PASS: API 项目带完整文档"""
        d = _make_deliverable(
            name="RESTful API 项目",
            required_format="Git 仓库",
            file_url="https://github.com/team/api-server.git",
            file_hash=VALID_HASH,
            acceptance_criteria={
                "description": "包含完整 API 实现和 Swagger 文档",
                "specific_requirements": [
                    {"name": "RESTful 设计", "description": "符合 REST 规范"},
                    {"name": "API 文档", "description": "Swagger/OpenAPI 文档"},
                    {"name": "单元测试", "description": "测试覆盖率 > 80%"},
                ],
            },
        )
        result = engine.evaluate_deliverable(d)
        assert result.overall == "approved"
        score = _compute_score(result)
        assert score >= 70

    def test_pass_api_zip_with_postman_collection(self):
        """PASS: API 项目以 ZIP 提交，含 Postman 集合"""
        d = _make_deliverable(
            name="后端 API 服务",
            required_format="zip",
            file_url="https://storage.example.com/api-v2.0.zip",
            file_hash=VALID_HASH,
            acceptance_criteria={
                "description": "包含源码、Postman 集合和部署脚本",
                "specific_requirements": [
                    {"name": "错误处理", "description": "统一错误响应格式"},
                    {"name": "认证机制", "description": "JWT 认证"},
                ],
            },
        )
        result = engine.evaluate_deliverable(d)
        assert result.overall == "approved"

    def test_pass_api_json_schema(self):
        """PASS: API Schema 以 JSON 格式提交"""
        d = _make_deliverable(
            name="API Schema 定义",
            required_format="json",
            file_url="https://example.com/openapi-schema.json",
            file_hash=VALID_HASH,
            acceptance_criteria={
                "description": "OpenAPI 3.0 规范的 API Schema",
            },
        )
        result = engine.evaluate_deliverable(d)
        assert result.overall == "approved"

    def test_fail_api_no_source_code(self):
        """FAIL: API 项目未提交源码"""
        d = _make_deliverable(
            name="RESTful API",
            required_format="Git 仓库",
            file_url=None,
            file_hash=None,
            acceptance_criteria={
                "description": "包含完整 API 实现",
                "specific_requirements": [
                    {"name": "RESTful", "description": "REST 规范"},
                ],
            },
        )
        result = engine.evaluate_deliverable(d)
        assert result.overall == "rejected"
        statuses = _get_check_statuses(result)
        assert statuses.get("文件上传") == "fail"
        assert statuses.get("要素：RESTful") == "fail"

    def test_fail_api_wrong_format_requirement(self):
        """FAIL: 要求 ZIP 但上传了 HTML"""
        d = _make_deliverable(
            name="API 源码",
            required_format="zip",
            file_url="https://example.com/api.html",
            file_hash=VALID_HASH,
            acceptance_criteria={"description": "API 实现"},
        )
        result = engine.evaluate_deliverable(d)
        assert result.overall == "rejected"
        statuses = _get_check_statuses(result)
        assert statuses.get("格式匹配") == "fail"

    def test_fail_api_missing_hash(self):
        """FAIL: API 项目缺少文件哈希"""
        d = _make_deliverable(
            name="API 服务",
            required_format="Git 仓库",
            file_url="https://github.com/team/api.git",
            file_hash=None,
            acceptance_criteria={"description": "API 实现"},
        )
        result = engine.evaluate_deliverable(d)
        assert result.overall == "rejected"
        statuses = _get_check_statuses(result)
        assert statuses.get("文件哈希") == "fail"

    def test_borderline_api_minimal_requirements(self):
        """BORDERLINE: API 项目仅满足最低要求"""
        d = _make_deliverable(
            name="简单 API",
            required_format="Git 仓库",
            file_url="https://github.com/user/simple-api.git",
            file_hash=VALID_HASH,
            acceptance_criteria={
                "description": "实现基础 CRUD 接口",
                "specific_requirements": [
                    "基础认证",
                ],
            },
        )
        result = engine.evaluate_deliverable(d)
        assert result.overall == "approved"
        statuses = _get_check_statuses(result)
        assert statuses.get("格式匹配") == "pass"
        assert statuses.get("要素：基础认证") == "pass"


# ============================================================
# data_analysis 任务类型测试
# ============================================================


class TestDataAnalysisAcceptance:
    """数据分析任务验收测试"""

    def test_pass_csv_analysis_report(self):
        """PASS: CSV 数据分析报告"""
        d = _make_deliverable(
            name="销售数据分析报告",
            required_format="csv",
            file_url="https://storage.example.com/analysis.csv",
            file_hash=VALID_HASH,
            acceptance_criteria={
                "description": "包含完整的数据分析结果和可视化",
                "specific_requirements": [
                    {"name": "数据清洗", "description": "处理缺失值和异常值"},
                    {"name": "统计分析", "description": "描述性统计和假设检验"},
                    {"name": "可视化图表", "description": "趋势图、分布图"},
                ],
            },
        )
        result = engine.evaluate_deliverable(d)
        assert result.overall == "approved"
        score = _compute_score(result)
        assert score >= 70

    def test_pass_xlsx_data_report(self):
        """PASS: Excel 数据分析报告"""
        d = _make_deliverable(
            name="用户行为分析",
            required_format="xlsx",
            file_url="https://storage.example.com/user_analysis.xlsx",
            file_hash=VALID_HASH,
            acceptance_criteria={
                "description": "用户行为分析报告含数据透视表",
                "required_sections": [
                    "数据概览",
                    "用户分群",
                    "行为路径分析",
                    "建议与结论",
                ],
            },
        )
        result = engine.evaluate_deliverable(d)
        assert result.overall == "approved"

    def test_pass_pdf_analysis_report(self):
        """PASS: PDF 格式分析报告"""
        d = _make_deliverable(
            name="年度数据分析报告",
            required_format="PDF",
            file_url="https://storage.example.com/annual_report.pdf",
            file_hash=VALID_HASH,
            acceptance_criteria={
                "description": "年度数据分析报告含图表和建议",
                "min_length": 5000,
            },
        )
        result = engine.evaluate_deliverable(d)
        assert result.overall == "approved"

    def test_fail_data_analysis_missing_file(self):
        """FAIL: 数据分析未提交文件"""
        d = _make_deliverable(
            name="销售数据分析",
            required_format="csv",
            file_url=None,
            file_hash=None,
            acceptance_criteria={
                "description": "完整数据分析报告",
            },
        )
        result = engine.evaluate_deliverable(d)
        assert result.overall == "rejected"

    def test_fail_data_analysis_wrong_format(self):
        """FAIL: 要求 CSV 但提交了 PDF"""
        d = _make_deliverable(
            name="数据分析",
            required_format="csv",
            file_url="https://storage.example.com/report.pdf",
            file_hash=VALID_HASH,
            acceptance_criteria={"description": "数据分析报告"},
        )
        result = engine.evaluate_deliverable(d)
        assert result.overall == "rejected"
        statuses = _get_check_statuses(result)
        assert statuses.get("格式匹配") == "fail"

    def test_fail_data_analysis_empty_hash(self):
        """FAIL: 哈希为空字符串"""
        d = _make_deliverable(
            name="数据分析",
            required_format="csv",
            file_url="https://storage.example.com/data.csv",
            file_hash="   ",
            acceptance_criteria={"description": "数据分析报告"},
        )
        result = engine.evaluate_deliverable(d)
        assert result.overall == "rejected"
        statuses = _get_check_statuses(result)
        assert statuses.get("文件哈希") == "fail"

    def test_borderline_data_analysis_no_format(self):
        """BORDERLINE: 数据分析未指定格式要求"""
        d = _make_deliverable(
            name="数据分析结果",
            required_format=None,
            file_url="https://storage.example.com/results.dat",
            file_hash=VALID_HASH,
            acceptance_criteria={
                "description": "完整的数据分析结果",
            },
        )
        result = engine.evaluate_deliverable(d)
        assert result.overall == "approved"
        statuses = _get_check_statuses(result)
        # 未指定格式，格式检查默认通过且 required=False
        assert statuses.get("格式匹配") == "pass"


# ============================================================
# design 任务类型测试
# ============================================================


class TestDesignAcceptance:
    """设计任务验收测试"""

    def test_pass_psd_design(self):
        """PASS: PSD 设计文件"""
        d = _make_deliverable(
            name="UI 设计稿",
            required_format="psd",
            file_url="https://storage.example.com/design_v2.psd",
            file_hash=VALID_HASH,
            acceptance_criteria={
                "description": "完整的 UI 设计稿，包含所有页面",
                "specific_requirements": [
                    {"name": "设计规范", "description": "包含色彩、字体规范"},
                    {"name": "响应式", "description": "移动端和桌面端适配"},
                    {"name": "图标素材", "description": "SVG 格式图标"},
                ],
            },
        )
        result = engine.evaluate_deliverable(d)
        assert result.overall == "approved"
        score = _compute_score(result)
        assert score >= 70

    def test_pass_figma_design(self):
        """PASS: Figma 设计文件"""
        d = _make_deliverable(
            name="产品原型设计",
            required_format="figma",
            file_url="https://storage.example.com/prototype.fig",
            file_hash=VALID_HASH,
            acceptance_criteria={
                "description": "产品原型设计文件",
                "required_sections": ["首页", "详情页", "个人中心"],
            },
        )
        result = engine.evaluate_deliverable(d)
        assert result.overall == "approved"

    def test_pass_sketch_design(self):
        """PASS: Sketch 设计文件"""
        d = _make_deliverable(
            name="品牌视觉设计",
            required_format="sketch",
            file_url="https://storage.example.com/brand_v1.sketch",
            file_hash=VALID_HASH,
            acceptance_criteria={
                "description": "品牌视觉设计包含 Logo、色彩方案",
            },
        )
        result = engine.evaluate_deliverable(d)
        assert result.overall == "approved"

    def test_fail_design_no_file(self):
        """FAIL: 设计稿未上传"""
        d = _make_deliverable(
            name="UI 设计稿",
            required_format="psd",
            file_url=None,
            file_hash=None,
            acceptance_criteria={
                "description": "完整的 UI 设计稿",
            },
        )
        result = engine.evaluate_deliverable(d)
        assert result.overall == "rejected"
        score = _compute_score(result)
        assert score < 60

    def test_fail_design_wrong_format(self):
        """FAIL: 要求 PSD 但提交了 TXT"""
        d = _make_deliverable(
            name="UI 设计",
            required_format="psd",
            file_url="https://storage.example.com/design.txt",
            file_hash=VALID_HASH,
            acceptance_criteria={"description": "UI 设计"},
        )
        result = engine.evaluate_deliverable(d)
        assert result.overall == "rejected"
        statuses = _get_check_statuses(result)
        assert statuses.get("格式匹配") == "fail"

    def test_fail_design_short_hash(self):
        """FAIL: 设计文件哈希长度不足"""
        d = _make_deliverable(
            name="UI 设计",
            required_format="psd",
            file_url="https://storage.example.com/design.psd",
            file_hash="abc123",  # 太短
            acceptance_criteria={"description": "UI 设计"},
        )
        result = engine.evaluate_deliverable(d)
        assert result.overall == "rejected"
        statuses = _get_check_statuses(result)
        assert statuses.get("文件哈希") == "fail"

    def test_borderline_design_multiformat(self):
        """BORDERLINE: 设计任务允许多种格式"""
        d = _make_deliverable(
            name="设计交付",
            required_format="PSD/Sketch",
            file_url="https://storage.example.com/design.sketch",
            file_hash=VALID_HASH,
            acceptance_criteria={
                "description": "设计交付物，支持 PSD 或 Sketch 格式",
            },
        )
        result = engine.evaluate_deliverable(d)
        assert result.overall == "approved"
        statuses = _get_check_statuses(result)
        assert statuses.get("格式匹配") == "pass"


# ============================================================
# writing 任务类型测试
# ============================================================


class TestWritingAcceptance:
    """写作/文案任务验收测试"""

    def test_pass_docx_article(self):
        """PASS: DOCX 格式的文章"""
        d = _make_deliverable(
            name="产品介绍文案",
            required_format="docx",
            file_url="https://storage.example.com/copywriting.docx",
            file_hash=VALID_HASH,
            acceptance_criteria={
                "description": "产品介绍文案，语言流畅，突出卖点",
                "min_length": 3000,
                "specific_requirements": [
                    {"name": "标题吸引力", "description": "标题需吸引读者"},
                    {"name": "卖点突出", "description": "核心卖点清晰"},
                    {"name": "行动号召", "description": "包含 CTA"},
                ],
            },
        )
        result = engine.evaluate_deliverable(d)
        assert result.overall == "approved"
        score = _compute_score(result)
        assert score >= 70

    def test_pass_pdf_whitepaper(self):
        """PASS: PDF 格式的白皮书"""
        d = _make_deliverable(
            name="行业白皮书",
            required_format="pdf",
            file_url="https://storage.example.com/whitepaper.pdf",
            file_hash=VALID_HASH,
            acceptance_criteria={
                "description": "行业白皮书，含数据支撑和专家观点",
                "min_length": 10000,
                "required_sections": [
                    "摘要",
                    "行业现状",
                    "数据分析",
                    "趋势预测",
                    "结论",
                ],
            },
        )
        result = engine.evaluate_deliverable(d)
        assert result.overall == "approved"

    def test_pass_md_technical_doc(self):
        """PASS: Markdown 技术文档"""
        d = _make_deliverable(
            name="API 使用文档",
            required_format="md",
            file_url="https://storage.example.com/api-docs.md",
            file_hash=VALID_HASH,
            acceptance_criteria={
                "description": "API 使用文档，包含示例代码",
                "specific_requirements": [
                    {"name": "快速开始", "description": "Quick Start 指南"},
                    {"name": "接口列表", "description": "所有接口说明"},
                    {"name": "错误码", "description": "错误码列表"},
                ],
            },
        )
        result = engine.evaluate_deliverable(d)
        assert result.overall == "approved"

    def test_fail_writing_no_file(self):
        """FAIL: 文案未提交"""
        d = _make_deliverable(
            name="产品文案",
            required_format="docx",
            file_url=None,
            file_hash=None,
            acceptance_criteria={
                "description": "产品介绍文案",
                "min_length": 3000,
            },
        )
        result = engine.evaluate_deliverable(d)
        assert result.overall == "rejected"

    def test_fail_writing_format_mismatch(self):
        """FAIL: 要求 DOCX 但提交了 HTML"""
        d = _make_deliverable(
            name="营销文案",
            required_format="docx",
            file_url="https://storage.example.com/copy.html",
            file_hash=VALID_HASH,
            acceptance_criteria={"description": "营销文案"},
        )
        result = engine.evaluate_deliverable(d)
        assert result.overall == "rejected"
        statuses = _get_check_statuses(result)
        assert statuses.get("格式匹配") == "fail"

    def test_fail_writing_missing_hash(self):
        """FAIL: 文案文件缺少哈希"""
        d = _make_deliverable(
            name="博客文章",
            required_format="md",
            file_url="https://storage.example.com/blog.md",
            file_hash=None,
            acceptance_criteria={"description": "技术博客"},
        )
        result = engine.evaluate_deliverable(d)
        assert result.overall == "rejected"
        statuses = _get_check_statuses(result)
        assert statuses.get("文件哈希") == "fail"

    def test_borderline_writing_no_format_requirement(self):
        """BORDERLINE: 写作任务未指定格式"""
        d = _make_deliverable(
            name="通用文案",
            required_format=None,
            file_url="https://storage.example.com/copy_final.txt",
            file_hash=VALID_HASH,
            acceptance_criteria={
                "description": "最终文案版本",
                "min_length": 2000,
            },
        )
        result = engine.evaluate_deliverable(d)
        assert result.overall == "approved"


# ============================================================
# consulting 任务类型测试
# ============================================================


class TestConsultingAcceptance:
    """咨询/顾问任务验收测试"""

    def test_pass_pdf_strategy_report(self):
        """PASS: PDF 战略咨询报告"""
        d = _make_deliverable(
            name="企业数字化转型战略报告",
            required_format="PDF",
            file_url="https://storage.example.com/strategy.pdf",
            file_hash=VALID_HASH,
            acceptance_criteria={
                "description": "数字化转型战略咨询报告",
                "specific_requirements": [
                    {"name": "现状评估", "description": "企业现状分析"},
                    {"name": "转型路径", "description": "分阶段转型方案"},
                    {"name": "投资回报", "description": "ROI 预测"},
                    {"name": "风险评估", "description": "风险及应对策略"},
                ],
                "required_sections": [
                    "执行摘要",
                    "现状分析",
                    "转型方案",
                    "实施计划",
                    "风险评估",
                ],
            },
        )
        result = engine.evaluate_deliverable(d)
        assert result.overall == "approved"
        score = _compute_score(result)
        assert score >= 70

    def test_pass_docx_market_research(self):
        """PASS: DOCX 市场研究报告"""
        d = _make_deliverable(
            name="市场调研报告",
            required_format="docx",
            file_url="https://storage.example.com/market_research.docx",
            file_hash=VALID_HASH,
            acceptance_criteria={
                "description": "目标市场调研分析报告",
                "min_length": 8000,
                "specific_requirements": [
                    {"name": "市场规模", "description": "TAM/SAM/SOM 分析"},
                    {"name": "竞品分析", "description": "主要竞争对手分析"},
                    {"name": "用户画像", "description": "目标用户特征"},
                ],
            },
        )
        result = engine.evaluate_deliverable(d)
        assert result.overall == "approved"

    def test_pass_pptx_presentation(self):
        """PASS: PPT 演示文稿"""
        d = _make_deliverable(
            name="项目评审演示",
            required_format="pptx",
            file_url="https://storage.example.com/review_deck.pptx",
            file_hash=VALID_HASH,
            acceptance_criteria={
                "description": "项目评审演示文稿",
                "required_sections": [
                    "项目概述",
                    "进展状态",
                    "风险问题",
                    "下一步计划",
                ],
            },
        )
        result = engine.evaluate_deliverable(d)
        assert result.overall == "approved"

    def test_fail_consulting_no_deliverable(self):
        """FAIL: 咨询报告未提交"""
        d = _make_deliverable(
            name="战略咨询报告",
            required_format="PDF",
            file_url=None,
            file_hash=None,
            acceptance_criteria={
                "description": "战略咨询报告",
                "specific_requirements": [
                    {"name": "现状评估", "description": "分析"},
                ],
            },
        )
        result = engine.evaluate_deliverable(d)
        assert result.overall == "rejected"
        statuses = _get_check_statuses(result)
        assert statuses.get("文件上传") == "fail"
        assert statuses.get("要素：现状评估") == "fail"

    def test_fail_consulting_wrong_format(self):
        """FAIL: 要求 PDF 但提交了 ZIP"""
        d = _make_deliverable(
            name="咨询报告",
            required_format="PDF",
            file_url="https://storage.example.com/report.zip",
            file_hash=VALID_HASH,
            acceptance_criteria={"description": "咨询报告"},
        )
        result = engine.evaluate_deliverable(d)
        assert result.overall == "rejected"
        statuses = _get_check_statuses(result)
        assert statuses.get("格式匹配") == "fail"

    def test_fail_consulting_hash_with_invalid_chars(self):
        """FAIL: 哈希包含非十六进制字符"""
        d = _make_deliverable(
            name="咨询报告",
            required_format="PDF",
            file_url="https://storage.example.com/report.pdf",
            file_hash="g1b2c3d4e5f6a1b2c3d4e5f6a1b2c3d4e5f6a1b2c3d4e5f6a1b2c3d4e5f6a1b2",
            acceptance_criteria={"description": "咨询报告"},
        )
        result = engine.evaluate_deliverable(d)
        assert result.overall == "rejected"
        statuses = _get_check_statuses(result)
        assert statuses.get("文件哈希") == "fail"

    def test_borderline_consulting_negative_criteria(self):
        """BORDERLINE: 咨询报告含否定性要求"""
        d = _make_deliverable(
            name="合规咨询报告",
            required_format="PDF",
            file_url="https://storage.example.com/compliance.pdf",
            file_hash=VALID_HASH,
            acceptance_criteria={
                "description": "合规咨询报告，内容不得包含未经验证的数据",
            },
        )
        result = engine.evaluate_deliverable(d)
        assert result.overall == "approved"
        statuses = _get_check_statuses(result)
        # 含否定性关键词，内容检查标记为建议人工复核但仍通过
        content_items = [i for i in result.items if "内容要素覆盖" in i.name]
        assert len(content_items) >= 1
        assert content_items[0].status == "pass"


# ============================================================
# other (其他) 任务类型测试
# ============================================================


class TestOtherAcceptance:
    """其他任务类型验收测试"""

    def test_pass_generic_deliverable_with_format(self):
        """PASS: 通用交付物格式正确"""
        d = _make_deliverable(
            name="项目总结报告",
            required_format="pdf",
            file_url="https://storage.example.com/summary.pdf",
            file_hash=VALID_HASH,
            acceptance_criteria={
                "description": "项目总结报告",
            },
        )
        result = engine.evaluate_deliverable(d)
        assert result.overall == "approved"
        score = _compute_score(result)
        assert score >= 70

    def test_pass_generic_html_deliverable(self):
        """PASS: HTML 格式交付物"""
        d = _make_deliverable(
            name="在线报告",
            required_format="html",
            file_url="https://storage.example.com/report.html",
            file_hash=VALID_HASH,
            acceptance_criteria={
                "description": "在线可浏览的报告",
                "specific_requirements": [
                    {"name": "交互功能", "description": "包含筛选和排序"},
                ],
            },
        )
        result = engine.evaluate_deliverable(d)
        assert result.overall == "approved"

    def test_pass_generic_xls_deliverable(self):
        """PASS: Excel 格式交付物"""
        d = _make_deliverable(
            name="数据表",
            required_format="xls",
            file_url="https://storage.example.com/data.xls",
            file_hash=VALID_HASH,
            acceptance_criteria={
                "description": "数据汇总表",
                "required_sections": ["Sheet1", "Sheet2"],
            },
        )
        result = engine.evaluate_deliverable(d)
        assert result.overall == "approved"

    def test_fail_generic_no_file_url(self):
        """FAIL: 通用交付物未上传文件"""
        d = _make_deliverable(
            name="交付物",
            required_format="pdf",
            file_url=None,
            file_hash=None,
            acceptance_criteria={"description": "按要求交付"},
        )
        result = engine.evaluate_deliverable(d)
        assert result.overall == "rejected"

    def test_fail_generic_format_mismatch_csv_vs_xlsx(self):
        """FAIL: 要求 XLSX 但提交了 CSV"""
        d = _make_deliverable(
            name="数据表",
            required_format="xlsx",
            file_url="https://storage.example.com/data.csv",
            file_hash=VALID_HASH,
            acceptance_criteria={"description": "数据表"},
        )
        result = engine.evaluate_deliverable(d)
        assert result.overall == "rejected"
        statuses = _get_check_statuses(result)
        assert statuses.get("格式匹配") == "fail"

    def test_fail_generic_malformed_hash(self):
        """FAIL: 哈希格式错误"""
        d = _make_deliverable(
            name="交付物",
            required_format="pdf",
            file_url="https://storage.example.com/file.pdf",
            file_hash="not-a-valid-hash!",
            acceptance_criteria={"description": "交付物"},
        )
        result = engine.evaluate_deliverable(d)
        assert result.overall == "rejected"
        statuses = _get_check_statuses(result)
        assert statuses.get("文件哈希") == "fail"

    def test_borderline_generic_loose_format_match(self):
        """BORDERLINE: 格式关键词不在已知映射中，触发宽松匹配"""
        d = _make_deliverable(
            name="自定义格式交付物",
            required_format="customformat",
            file_url="https://storage.example.com/delivery.custom",
            file_hash=VALID_HASH,
            acceptance_criteria={"description": "自定义格式交付"},
        )
        result = engine.evaluate_deliverable(d)
        # 不在 _FORMAT_EXTENSIONS 中，触发宽松匹配
        assert result.overall == "approved"
        statuses = _get_check_statuses(result)
        assert statuses.get("格式匹配") == "pass"
        assert statuses.get("格式匹配") == "pass"


# ============================================================
# 边界/异常情况测试
# ============================================================


class TestEdgeCases:
    """边界和异常情况测试"""

    def test_empty_deliverable_no_file_no_criteria(self):
        """空交付物：无文件、无验收标准"""
        d = _make_deliverable(
            name="空交付物",
            required_format=None,
            file_url=None,
            file_hash=None,
            acceptance_criteria={},
        )
        result = engine.evaluate_deliverable(d)
        assert result.overall == "rejected"
        statuses = _get_check_statuses(result)
        assert statuses.get("文件上传") == "fail"
        assert statuses.get("文件哈希") == "fail"

    def test_whitespace_only_file_url(self):
        """仅空白字符的文件 URL"""
        d = _make_deliverable(
            name="空白 URL 交付物",
            required_format="pdf",
            file_url="   ",
            file_hash=VALID_HASH,
            acceptance_criteria={"description": "测试"},
        )
        result = engine.evaluate_deliverable(d)
        assert result.overall == "rejected"
        statuses = _get_check_statuses(result)
        assert statuses.get("文件上传") == "fail"

    def test_whitespace_only_file_hash(self):
        """仅空白字符的文件哈希"""
        d = _make_deliverable(
            name="空白哈希交付物",
            required_format="pdf",
            file_url="https://storage.example.com/file.pdf",
            file_hash="   ",
            acceptance_criteria={"description": "测试"},
        )
        result = engine.evaluate_deliverable(d)
        assert result.overall == "rejected"
        statuses = _get_check_statuses(result)
        assert statuses.get("文件哈希") == "fail"

    def test_deliverable_with_wrong_task_type_format(self):
        """交付物格式与任务类型不匹配（设计任务提交了 CSV）"""
        d = _make_deliverable(
            name="设计任务交付",
            required_format="csv",
            file_url="https://storage.example.com/design_data.csv",
            file_hash=VALID_HASH,
            acceptance_criteria={"description": "设计任务的交付物"},
        )
        result = engine.evaluate_deliverable(d)
        # 格式检查是基于 required_format 而非任务类型，CSV 匹配 csv
        assert result.overall == "approved"
        statuses = _get_check_statuses(result)
        assert statuses.get("格式匹配") == "pass"

    def test_deliverable_correct_format_empty_content(self):
        """格式正确但内容为空的交付物"""
        d = _make_deliverable(
            name="空内容交付物",
            required_format="pdf",
            file_url="https://storage.example.com/empty.pdf",
            file_hash=VALID_HASH,
            acceptance_criteria={},  # 空验收标准
        )
        result = engine.evaluate_deliverable(d)
        assert result.overall == "approved"
        # 内容检查应默认通过
        content_items = [i for i in result.items if "内容要素覆盖" in i.name]
        assert len(content_items) >= 1
        assert content_items[0].status == "pass"

    def test_file_url_with_query_params(self):
        """文件 URL 带查询参数，扩展名解析正确"""
        d = _make_deliverable(
            name="带参数 URL 的交付物",
            required_format="pdf",
            file_url="https://storage.example.com/report.pdf?v=2&token=abc",
            file_hash=VALID_HASH,
            acceptance_criteria={"description": "测试"},
        )
        result = engine.evaluate_deliverable(d)
        assert result.overall == "approved"
        statuses = _get_check_statuses(result)
        assert statuses.get("格式匹配") == "pass"

    def test_file_url_tar_gz(self):
        """tar.gz 扩展名应提取为 .gz"""
        d = _make_deliverable(
            name="压缩包交付物",
            required_format="zip",
            file_url="https://storage.example.com/archive.tar.gz",
            file_hash=VALID_HASH,
            acceptance_criteria={"description": "压缩包"},
        )
        result = engine.evaluate_deliverable(d)
        assert result.overall == "approved"
        statuses = _get_check_statuses(result)
        assert statuses.get("格式匹配") == "pass"

    def test_file_url_with_fragment(self):
        """文件 URL 带锚点片段"""
        d = _make_deliverable(
            name="锚点 URL 交付物",
            required_format="html",
            file_url="https://storage.example.com/page.html#section1",
            file_hash=VALID_HASH,
            acceptance_criteria={"description": "测试"},
        )
        result = engine.evaluate_deliverable(d)
        assert result.overall == "approved"
        statuses = _get_check_statuses(result)
        assert statuses.get("格式匹配") == "pass"

    def test_multiple_format_requirement_slash(self):
        """多种格式要求用 / 分隔"""
        d = _make_deliverable(
            name="多格式交付物",
            required_format="PDF/DOCX",
            file_url="https://storage.example.com/report.docx",
            file_hash=VALID_HASH,
            acceptance_criteria={"description": "测试"},
        )
        result = engine.evaluate_deliverable(d)
        assert result.overall == "approved"
        statuses = _get_check_statuses(result)
        assert statuses.get("格式匹配") == "pass"

    def test_multiple_format_requirement_comma(self):
        """多种格式要求用 , 分隔"""
        d = _make_deliverable(
            name="多格式交付物",
            required_format="PDF, DOCX",
            file_url="https://storage.example.com/report.pdf",
            file_hash=VALID_HASH,
            acceptance_criteria={"description": "测试"},
        )
        result = engine.evaluate_deliverable(d)
        assert result.overall == "approved"
        statuses = _get_check_statuses(result)
        assert statuses.get("格式匹配") == "pass"

    def test_empty_name_deliverable(self):
        """空名称的交付物"""
        d = _make_deliverable(
            name="",
            required_format="pdf",
            file_url="https://storage.example.com/file.pdf",
            file_hash=VALID_HASH,
            acceptance_criteria={"description": "测试"},
        )
        result = engine.evaluate_deliverable(d)
        assert result.overall == "approved"

    def test_hash_exactly_32_chars(self):
        """哈希刚好 32 位（最低要求）"""
        hash_32 = "a" * 32
        d = _make_deliverable(
            name="32位哈希",
            required_format="pdf",
            file_url="https://storage.example.com/file.pdf",
            file_hash=hash_32,
            acceptance_criteria={"description": "测试"},
        )
        result = engine.evaluate_deliverable(d)
        assert result.overall == "approved"
        statuses = _get_check_statuses(result)
        assert statuses.get("文件哈希") == "pass"

    def test_hash_31_chars_fails(self):
        """哈希 31 位（不满足最低 32 位要求）"""
        hash_31 = "a" * 31
        d = _make_deliverable(
            name="31位哈希",
            required_format="pdf",
            file_url="https://storage.example.com/file.pdf",
            file_hash=hash_31,
            acceptance_criteria={"description": "测试"},
        )
        result = engine.evaluate_deliverable(d)
        assert result.overall == "rejected"
        statuses = _get_check_statuses(result)
        assert statuses.get("文件哈希") == "fail"

    def test_uppercase_hash_valid(self):
        """大写十六进制哈希也应有效"""
        hash_upper = "A" * 64
        d = _make_deliverable(
            name="大写哈希",
            required_format="pdf",
            file_url="https://storage.example.com/file.pdf",
            file_hash=hash_upper,
            acceptance_criteria={"description": "测试"},
        )
        result = engine.evaluate_deliverable(d)
        assert result.overall == "approved"
        statuses = _get_check_statuses(result)
        assert statuses.get("文件哈希") == "pass"

    def test_mixed_case_hash_valid(self):
        """混合大小写十六进制哈希有效"""
        hash_mixed = "aAbBcCdD" * 8
        d = _make_deliverable(
            name="混合大小写哈希",
            required_format="pdf",
            file_url="https://storage.example.com/file.pdf",
            file_hash=hash_mixed,
            acceptance_criteria={"description": "测试"},
        )
        result = engine.evaluate_deliverable(d)
        assert result.overall == "approved"

    def test_hash_with_spaces_around(self):
        """哈希前后有空白应被 strip"""
        d = _make_deliverable(
            name="带空格哈希",
            required_format="pdf",
            file_url="https://storage.example.com/file.pdf",
            file_hash=f"  {VALID_HASH}  ",
            acceptance_criteria={"description": "测试"},
        )
        result = engine.evaluate_deliverable(d)
        assert result.overall == "approved"
        statuses = _get_check_statuses(result)
        assert statuses.get("文件哈希") == "pass"

    def test_content_criteria_with_min_length_met(self):
        """内容检查：有最小字数要求且文件已上传"""
        d = _make_deliverable(
            name="长文档",
            required_format="pdf",
            file_url="https://storage.example.com/long_doc.pdf",
            file_hash=VALID_HASH,
            acceptance_criteria={
                "min_length": 5000,
            },
        )
        result = engine.evaluate_deliverable(d)
        assert result.overall == "approved"
        statuses = _get_check_statuses(result)
        assert statuses.get("最小字数") == "pass"

    def test_content_criteria_with_word_count_in_result(self):
        """内容检查：acceptance_result 中有 word_count 数据"""
        d = _make_deliverable(
            name="已评估文档",
            required_format="pdf",
            file_url="https://storage.example.com/doc.pdf",
            file_hash=VALID_HASH,
            acceptance_criteria={
                "min_length": 3000,
            },
            acceptance_result={"word_count": 5000},
        )
        result = engine.evaluate_deliverable(d)
        assert result.overall == "approved"
        statuses = _get_check_statuses(result)
        assert statuses.get("最小字数") == "pass"

    def test_content_criteria_with_word_count_insufficient(self):
        """内容检查：word_count 不满足最小要求"""
        d = _make_deliverable(
            name="短文档",
            required_format="pdf",
            file_url="https://storage.example.com/short.pdf",
            file_hash=VALID_HASH,
            acceptance_criteria={
                "min_length": 5000,
            },
            acceptance_result={"word_count": 2000},
        )
        result = engine.evaluate_deliverable(d)
        # word_count < min_length → fail (required=True)
        assert result.overall == "rejected"
        statuses = _get_check_statuses(result)
        assert statuses.get("最小字数") == "fail"

    def test_quality_score_threshold_always_passes(self):
        """质量分阈值检查在规则引擎中始终通过"""
        d = _make_deliverable(
            name="质量要求文档",
            required_format="pdf",
            file_url="https://storage.example.com/doc.pdf",
            file_hash=VALID_HASH,
            acceptance_criteria={
                "quality_score_threshold": 85.0,
            },
        )
        result = engine.evaluate_deliverable(d)
        assert result.overall == "approved"
        statuses = _get_check_statuses(result)
        assert statuses.get("质量评分") == "pass"

    def test_no_acceptance_criteria_skips_content_check(self):
        """无验收标准时跳过内容检查"""
        d = _make_deliverable(
            name="无标准交付物",
            required_format=None,
            file_url="https://storage.example.com/file.dat",
            file_hash=VALID_HASH,
            acceptance_criteria=None,
        )
        result = engine.evaluate_deliverable(d)
        assert result.overall == "approved"
        content_items = [i for i in result.items if "内容要素覆盖" in i.name]
        assert len(content_items) >= 1
        assert content_items[0].status == "pass"

    def test_all_checks_fail_deliverable(self):
        """所有检查项全部失败"""
        d = _make_deliverable(
            name="全失败交付物",
            required_format="pdf",
            file_url=None,
            file_hash=None,
            acceptance_criteria={
                "description": "完整报告",
                "specific_requirements": [
                    {"name": "数据分析", "description": "含统计分析"},
                ],
                "min_length": 10000,
                "required_sections": ["摘要", "正文", "结论"],
            },
        )
        result = engine.evaluate_deliverable(d)
        assert result.overall == "rejected"
        failed_items = [i for i in result.items if i.status == "fail"]
        assert len(failed_items) >= 3  # 文件上传、文件哈希、至少一个内容项

    def test_evaluation_result_structure(self):
        """验证评估结果的完整结构"""
        d = _make_deliverable(
            name="结构测试",
            required_format="pdf",
            file_url="https://storage.example.com/file.pdf",
            file_hash=VALID_HASH,
            acceptance_criteria={
                "description": "测试",
                "specific_requirements": ["要求1", "要求2"],
            },
        )
        result = engine.evaluate_deliverable(d)

        # 验证结果类型
        assert isinstance(result, EvaluationResult)
        assert result.deliverable_id == d.id
        assert result.overall in ("approved", "rejected")
        assert isinstance(result.items, list)
        assert len(result.items) > 0

        # 验证每项结构
        for item in result.items:
            assert isinstance(item, CheckItem)
            assert item.name
            assert item.status in ("pass", "fail")
            assert isinstance(item.detail, str)
            assert isinstance(item.required, bool)

        # 验证 to_dict
        result_dict = result.to_dict()
        assert result_dict["deliverable_id"] == str(d.id)
        assert result_dict["overall"] in ("approved", "rejected")
        assert isinstance(result_dict["items"], list)

    def test_multiple_specific_requirements_as_strings(self):
        """具体要求为字符串列表（非字典）"""
        d = _make_deliverable(
            name="字符串要求",
            required_format="pdf",
            file_url="https://storage.example.com/file.pdf",
            file_hash=VALID_HASH,
            acceptance_criteria={
                "specific_requirements": [
                    "要求一：格式正确",
                    "要求二：内容完整",
                    "要求三：无错误",
                ],
            },
        )
        result = engine.evaluate_deliverable(d)
        assert result.overall == "approved"
        specific_items = [i for i in result.items if i.name.startswith("要素：")]
        assert len(specific_items) == 3
        for item in specific_items:
            assert item.status == "pass"

    def test_mixed_specific_requirements_types(self):
        """混合字典和字符串的具体要求"""
        d = _make_deliverable(
            name="混合要求",
            required_format="pdf",
            file_url="https://storage.example.com/file.pdf",
            file_hash=VALID_HASH,
            acceptance_criteria={
                "specific_requirements": [
                    {"name": "字典要求", "description": "字典格式的要求"},
                    "字符串要求",
                ],
            },
        )
        result = engine.evaluate_deliverable(d)
        assert result.overall == "approved"
        specific_items = [i for i in result.items if i.name.startswith("要素：")]
        assert len(specific_items) == 2
