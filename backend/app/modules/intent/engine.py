"""
2C1H 意图建模引擎
2 Context 1 Hypothesis：基于双上下文（用户输入 + 环境上下文）提出一个假设性意图

核心功能：
- analyze_intent: 分析用户自然语言输入，提取核心意图
- generate_blueprint: 根据意图分析生成结构化蓝图
- generate_questions: 根据蓝图生成追问列表（分级：required/important/optional）
- skip_question: 跳过追问并记录原因
- calculate_skip_rate: 计算跳过率
- pending_clarifications: 获取待澄清项

不调用真实 LLM API，使用规则引擎 + 模板模拟
"""

from __future__ import annotations

import re
import uuid
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

import structlog

logger = structlog.get_logger("modules.intent.engine")


# ============================================================
# 数据结构
# ============================================================

@dataclass
class IntentAnalysis:
    """意图分析结果"""
    task_type: str           # 推断的任务类型
    summary: str             # 意图摘要
    keywords: List[str]      # 关键词列表
    confidence: float        # 置信度 0-1
    raw_input: str           # 原始输入


@dataclass
class BlueprintData:
    """结构化蓝图数据"""
    task_type: str
    title: str
    description: str
    requirements: List[str]
    constraints: List[str]
    deliverable_hints: List[str]


@dataclass
class Question:
    """追问项"""
    id: str                  # 追问ID
    text: str                # 追问内容
    priority: str            # 优先级：required / important / optional
    skipped: bool = False    # 是否已跳过
    skip_reason: Optional[str] = None  # 跳过原因


# ============================================================
# 关键词 → 任务类型映射表
# ============================================================

_TASK_TYPE_KEYWORDS: Dict[str, List[str]] = {
    "development": [
        "开发", "编程", "代码", "软件", "网站", "APP", "应用", "系统",
        "程序", "前端", "后端", "接口", "API", "数据库", "小程序",
        "微信", "H5", "平台", "功能", "模块", "bug", "修复",
        "python", "java", "react", "vue", "node", "部署",
    ],
    "design": [
        "设计", "UI", "UX", "界面", "图标", "logo", "海报", "品牌",
        "视觉", "配色", "排版", "插画", "动效", "原型", "交互",
        "平面", "网页设计", "APP设计", "包装",
    ],
    "copywriting": [
        "文案", "写作", "撰写", "文章", "内容", "营销", "推广",
        "广告", "公众号", "软文", "策划", "脚本", "视频文案",
        "产品描述", "新闻稿", "PR稿",
    ],
    "translation": [
        "翻译", "英译中", "中译英", "日语", "韩语", "法语",
        "德语", "西班牙语", "本地化", "多语言", "字幕",
    ],
    "data_labeling": [
        "标注", "数据标注", "标签", "分类", "图像标注", "文本标注",
        "语音标注", "标注任务", "样本", "训练数据",
    ],
    "consulting": [
        "咨询", "顾问", "方案", "规划", "分析", "诊断", "评估",
        "策略", "建议", "优化", "改进",
    ],
}


# ============================================================
# 任务类型 → 蓝图模板
# ============================================================

_BLUEPRINT_TEMPLATES: Dict[str, Dict[str, Any]] = {
    "development": {
        "title_tpl": "开发任务：{summary}",
        "description_tpl": "需要完成软件开发相关工作。{summary}",
        "requirements": [
            "明确技术栈和框架要求",
            "定义功能需求和验收标准",
            "确认交付物格式（源代码、部署包等）",
        ],
        "constraints": [
            "代码需通过基础质量检查",
            "需提供必要的技术文档",
        ],
        "deliverable_hints": [
            "源代码仓库访问权限",
            "部署文档",
            "测试报告",
        ],
    },
    "design": {
        "title_tpl": "设计任务：{summary}",
        "description_tpl": "需要完成设计相关工作。{summary}",
        "requirements": [
            "明确设计风格和参考",
            "提供品牌规范（如有）",
            "确认交付文件格式",
        ],
        "constraints": [
            "需提供源文件（PSD/AI/Sketch等）",
            "符合品牌调性",
        ],
        "deliverable_hints": [
            "设计源文件",
            "切图资源",
            "设计规范文档",
        ],
    },
    "copywriting": {
        "title_tpl": "文案任务：{summary}",
        "description_tpl": "需要完成文案撰写相关工作。{summary}",
        "requirements": [
            "明确文案用途和目标受众",
            "确认字数和格式要求",
            "提供参考资料或竞品文案",
        ],
        "constraints": [
            "内容原创，不得抄袭",
            "符合平台发布规范",
        ],
        "deliverable_hints": [
            "文案终稿",
            "SEO关键词建议",
        ],
    },
    "translation": {
        "title_tpl": "翻译任务：{summary}",
        "description_tpl": "需要完成翻译相关工作。{summary}",
        "requirements": [
            "明确源语言和目标语言",
            "确认专业领域（法律/技术/医学等）",
            "提供术语表（如有）",
        ],
        "constraints": [
            "翻译准确，语义通顺",
            "保留原文格式",
        ],
        "deliverable_hints": [
            "翻译稿",
            "术语对照表",
        ],
    },
    "data_labeling": {
        "title_tpl": "数据标注任务：{summary}",
        "description_tpl": "需要完成数据标注相关工作。{summary}",
        "requirements": [
            "明确标注规范和标签体系",
            "提供标注工具或格式要求",
            "确认样本量和交付周期",
        ],
        "constraints": [
            "标注准确率需达到约定标准",
            "需抽样质检",
        ],
        "deliverable_hints": [
            "标注数据文件",
            "质检报告",
        ],
    },
    "consulting": {
        "title_tpl": "咨询任务：{summary}",
        "description_tpl": "需要完成咨询/分析相关工作。{summary}",
        "requirements": [
            "明确咨询范围和目标",
            "提供必要的背景资料",
            "确认交付报告格式",
        ],
        "constraints": [
            "分析结论需有数据支撑",
            "需保密敏感信息",
        ],
        "deliverable_hints": [
            "分析报告",
            "优化建议方案",
        ],
    },
    "other": {
        "title_tpl": "其他任务：{summary}",
        "description_tpl": "需要完成相关工作。{summary}",
        "requirements": [
            "明确任务目标和范围",
            "确认交付标准",
        ],
        "constraints": [
            "按时交付",
        ],
        "deliverable_hints": [
            "任务交付物",
        ],
    },
}


# ============================================================
# 任务类型 → 追问模板
# ============================================================

_QUESTION_TEMPLATES: Dict[str, List[Dict[str, str]]] = {
    "development": [
        {"text": "请确认技术栈要求（如 Python/Java/Go + 前端框架）", "priority": "required"},
        {"text": "预期的并发量和性能要求是什么？", "priority": "important"},
        {"text": "是否需要对接第三方系统或API？", "priority": "important"},
        {"text": "代码需要部署到什么环境（云服务器/容器/Serverless）？", "priority": "optional"},
        {"text": "是否有现成的代码仓库或技术文档可以参考？", "priority": "optional"},
    ],
    "design": [
        {"text": "请提供品牌色、字体等视觉规范（如有）", "priority": "required"},
        {"text": "目标用户群体是哪些？风格偏好是什么？", "priority": "required"},
        {"text": "需要提供哪些尺寸/格式的设计稿？", "priority": "important"},
        {"text": "是否有竞品设计可以参考？", "priority": "optional"},
    ],
    "copywriting": [
        {"text": "文案的目标受众是谁？", "priority": "required"},
        {"text": "文案发布在什么平台？有无字数限制？", "priority": "required"},
        {"text": "是否需要包含特定关键词或SEO优化？", "priority": "important"},
        {"text": "品牌调性和语言风格有无要求？", "priority": "optional"},
    ],
    "translation": [
        {"text": "源语言和目标语言分别是什么？", "priority": "required"},
        {"text": "文档涉及什么专业领域？", "priority": "required"},
        {"text": "是否有术语表或翻译记忆库？", "priority": "important"},
        {"text": "翻译完成后是否需要审校？", "priority": "optional"},
    ],
    "data_labeling": [
        {"text": "请描述标注规范和标签体系", "priority": "required"},
        {"text": "数据量大约是多少？", "priority": "required"},
        {"text": "使用什么标注工具或输出格式？", "priority": "important"},
        {"text": "质量验收标准是什么（如准确率要求）？", "priority": "important"},
    ],
    "consulting": [
        {"text": "咨询的核心问题或目标是什么？", "priority": "required"},
        {"text": "需要分析哪些数据或资料？", "priority": "required"},
        {"text": "期望的交付报告格式和深度？", "priority": "important"},
        {"text": "是否有时间敏感性要求？", "priority": "optional"},
    ],
    "other": [
        {"text": "请详细描述任务目标和预期结果", "priority": "required"},
        {"text": "验收标准是什么？", "priority": "required"},
        {"text": "是否有参考资料或示例？", "priority": "important"},
    ],
}


# ============================================================
# 2C1H 引擎核心类
# ============================================================

class IntentEngine:
    """
    2C1H（2 Context 1 Hypothesis）意图建模引擎

    工作原理：
    1. Context 1：用户自然语言输入
    2. Context 2：环境上下文（行业、预算等）
    3. Hypothesis：通过规则引擎推断用户意图假设
    """

    def analyze_intent(
        self,
        user_input: str,
        context: Optional[Dict[str, Any]] = None,
    ) -> IntentAnalysis:
        """
        分析用户自然语言输入，提取核心意图

        :param user_input: 用户输入的自然语言文本
        :param context: 上下文信息（可选）
        :return: IntentAnalysis 意图分析结果
        """
        context = context or {}
        logger.info("analyzing_intent", input_length=len(user_input))

        # 1. 提取关键词
        keywords = self._extract_keywords(user_input)

        # 2. 推断任务类型
        task_type, confidence = self._infer_task_type(user_input, keywords, context)

        # 3. 生成意图摘要
        summary = self._generate_summary(user_input, task_type)

        result = IntentAnalysis(
            task_type=task_type,
            summary=summary,
            keywords=keywords,
            confidence=confidence,
            raw_input=user_input,
        )

        logger.info(
            "intent_analyzed",
            task_type=task_type,
            confidence=confidence,
            keyword_count=len(keywords),
        )
        return result

    def generate_blueprint(self, analysis: IntentAnalysis) -> BlueprintData:
        """
        根据意图分析生成结构化蓝图

        :param analysis: 意图分析结果
        :return: BlueprintData 结构化蓝图
        """
        template = _BLUEPRINT_TEMPLATES.get(
            analysis.task_type, _BLUEPRINT_TEMPLATES["other"]
        )

        title = template["title_tpl"].format(summary=analysis.summary[:50])
        description = template["description_tpl"].format(summary=analysis.summary)

        # 根据关键词动态调整需求列表
        requirements = list(template["requirements"])
        if len(analysis.keywords) > 0:
            requirements.append(
                f"关键词参考：{'、'.join(analysis.keywords[:5])}"
            )

        blueprint = BlueprintData(
            task_type=analysis.task_type,
            title=title,
            description=description,
            requirements=requirements,
            constraints=list(template["constraints"]),
            deliverable_hints=list(template["deliverable_hints"]),
        )

        logger.info(
            "blueprint_generated",
            task_type=analysis.task_type,
            title=title,
            requirement_count=len(requirements),
        )
        return blueprint

    def generate_questions(self, blueprint_content: Dict[str, Any]) -> List[Question]:
        """
        根据蓝图内容生成追问列表

        :param blueprint_content: 蓝图内容字典（需包含 task_type 字段）
        :return: 追问列表
        """
        task_type = blueprint_content.get("task_type", "other")
        templates = _QUESTION_TEMPLATES.get(
            task_type, _QUESTION_TEMPLATES["other"]
        )

        questions = []
        for idx, tpl in enumerate(templates):
            q = Question(
                id=f"q_{task_type}_{idx + 1}",
                text=tpl["text"],
                priority=tpl["priority"],
                skipped=False,
                skip_reason=None,
            )
            questions.append(q)

        logger.info(
            "questions_generated",
            task_type=task_type,
            total=len(questions),
            required=sum(1 for q in questions if q.priority == "required"),
        )
        return questions

    # ----------------------------------------------------------
    # 内部方法
    # ----------------------------------------------------------

    def _extract_keywords(self, text: str) -> List[str]:
        """从文本中提取关键词（简单规则引擎）"""
        keywords: List[str] = []

        # 遍历所有任务类型的关键词表，匹配出现的关键词
        for _task_type, kw_list in _TASK_TYPE_KEYWORDS.items():
            for kw in kw_list:
                if kw.lower() in text.lower() and kw not in keywords:
                    keywords.append(kw)

        # 如果没有匹配到预设关键词，尝试按空格/标点分词提取
        if not keywords:
            # 提取中文词组（2-6字）和英文单词
            cn_words = re.findall(r'[\u4e00-\u9fff]{2,6}', text)
            en_words = re.findall(r'[a-zA-Z]{3,}', text)
            seen = set()
            for w in cn_words + en_words:
                wl = w.lower()
                if wl not in seen and len(wl) >= 2:
                    seen.add(wl)
                    keywords.append(w)
                if len(keywords) >= 10:
                    break

        return keywords[:10]

    def _infer_task_type(
        self,
        text: str,
        keywords: List[str],
        context: Dict[str, Any],
    ) -> tuple[str, float]:
        """
        推断任务类型

        返回 (task_type, confidence)
        """
        # 如果上下文中指定了任务类型，直接使用
        ctx_type = context.get("task_type")
        if ctx_type and ctx_type in _BLUEPRINT_TEMPLATES:
            return ctx_type, 0.95

        # 统计每个任务类型的匹配关键词数
        scores: Dict[str, int] = {}
        text_lower = text.lower()
        for task_type, kw_list in _TASK_TYPE_KEYWORDS.items():
            score = 0
            for kw in kw_list:
                if kw.lower() in text_lower:
                    score += 1
            if score > 0:
                scores[task_type] = score

        if not scores:
            return "other", 0.3

        # 选择得分最高的任务类型
        best_type = max(scores, key=scores.get)  # type: ignore[arg-type]
        best_score = scores[best_type]

        # 根据匹配数量计算置信度（匹配越多越自信）
        confidence = min(0.5 + best_score * 0.1, 0.95)

        return best_type, round(confidence, 2)

    def _generate_summary(self, text: str, task_type: str) -> str:
        """生成意图摘要"""
        # 截取前100字作为摘要基础
        clean_text = text.strip()
        if len(clean_text) <= 100:
            return clean_text

        # 尝试在句号/逗号处截断
        for sep in ['。', '，', '；', '！', '？', '.', ',', ';', '!', '?']:
            pos = clean_text.find(sep, 50, 100)
            if pos > 0:
                return clean_text[: pos + 1]

        return clean_text[:100] + "..."


# ============================================================
# 追问管理（内存存储，配合蓝图内容持久化）
# ============================================================

def skip_question_in_list(
    questions: List[Dict[str, Any]],
    question_id: str,
    reason: str,
) -> Optional[Dict[str, Any]]:
    """
    在追问列表中跳过指定追问

    :param questions: 追问列表（字典格式）
    :param question_id: 要跳过的追问ID
    :param reason: 跳过原因
    :return: 被跳过的追问，未找到返回 None
    """
    for q in questions:
        if q["id"] == question_id:
            q["skipped"] = True
            q["skip_reason"] = reason
            logger.info(
                "question_skipped",
                question_id=question_id,
                reason=reason,
            )
            return q
    return None


def calculate_skip_rate_from_list(
    questions: List[Dict[str, Any]],
) -> float:
    """
    计算追问跳过率

    :param questions: 追问列表
    :return: 跳过率 0-1
    """
    if not questions:
        return 0.0
    skipped = sum(1 for q in questions if q.get("skipped", False))
    return round(skipped / len(questions), 4)


def get_pending_questions(
    questions: List[Dict[str, Any]],
) -> List[Dict[str, Any]]:
    """
    获取待澄清项（未跳过、未回答的追问）

    :param questions: 追问列表
    :return: 待澄清追问列表
    """
    return [q for q in questions if not q.get("skipped", False)]


# 模块级引擎实例（单例）
intent_engine = IntentEngine()
