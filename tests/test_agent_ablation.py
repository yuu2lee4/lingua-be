"""
Agent 消融实验：使用完整 Agent 工作流比较不同模型的翻译效果

测试目标：
1. 使用分阶段 Agent 流程进行翻译（按语言分批）
2. 对比 GPT-5-mini, Claude Sonnet 4.5 和 Gemini 3 Flash 三种模型
3. 支持按 batch 批量翻译（按语言维度批处理）
4. 导出 CSV 对比结果

批处理逻辑：
- 例如 100 个文本，4 种目标语言，batch_size=20
- 翻译阶段：每种语言翻译 5 轮（100/20=5），合计 20 轮（5*4=20）
- 质量评审：同翻译阶段，按语言批处理
- 一致性评审：对目标语言循环组合评估，如 4 种语言有 4 种组合 (1,2), (2,3), (3,4), (4,1)
"""

import asyncio
import csv
import datetime
import json
import logging
import os
import time
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Any

# 减少第三方库的日志噪音
logging.getLogger("httpx").setLevel(logging.WARNING)
logging.getLogger("httpcore").setLevel(logging.WARNING)
logging.getLogger("openai").setLevel(logging.WARNING)
logging.getLogger("anthropic").setLevel(logging.WARNING)
logging.getLogger("google").setLevel(logging.WARNING)
logging.getLogger("urllib3").setLevel(logging.WARNING)

# 加载 Apollo 配置（设置 API 密钥等环境变量）
try:
    from app.config.configuration import Config  # noqa: F401

    print("[config] Apollo 配置加载成功")
except Exception as e:
    print(f"[config] Apollo 配置加载失败: {e}，将使用环境变量")

import pytest

from app.agents.review.consistency_agent import ConsistencyReviewAgent
from app.agents.review.quality_agent import QualityReviewAgent
from app.agents.translation_agent import TranslationAgent
from app.clients.llm_client import UnifiedLLMClient
from app.core.constants import (
    QUALITY_THRESHOLD,
    LanguageCode,
    get_language_name,
)
from app.schemas.glossary import Glossary
from app.schemas.review import ReviewFeedback
from app.schemas.translation import TranslationItem
from app.services.glossary_service import glossary_service

# 配置路径
BASE_DIR = Path(__file__).parent.parent
DATA_DIR = BASE_DIR / "examples"
GLOSSARY_PATH = DATA_DIR / "glossary.json"
SOURCE_PATH = DATA_DIR / "en.json"
OUTPUT_DIR = BASE_DIR / "tests" / "agent_ablation_results"


class ModelType(str, Enum):
    """测试模型类型"""

    GPT_MINI = "gpt-5-mini"
    GPT = "gpt-5.2"
    CLAUDE_SONNET = "claude-sonnet-4-5-20250929"
    CLAUDE_OPUS = "claude-opus-4-6"
    GEMINI_FLASH = "gemini-3-flash-preview"
    GEMINI_PRO = "gemini-3-pro-preview"


# 默认评审模型列表
DEFAULT_REVIEW_MODELS = [ModelType.CLAUDE_SONNET]


# AI 支持的目标语言（排除源语言英语）
DEFAULT_TARGET_LANGUAGES = [
    LanguageCode.ZH_CN.value,
    LanguageCode.ZH_TW.value,
    LanguageCode.KO_KR.value,
]


@dataclass
class AgentTranslationResult:
    """Agent 翻译结果"""

    source_key: str
    source_text: str
    model: ModelType  # 翻译模型
    review_model: ModelType  # 评审模型
    target_lang: str
    translated_text: str
    quality_score: int | None = None
    quality_feedback: str | None = None
    latency_ms: float = 0.0
    retry_count: int = 0
    glossary_terms_found: list[str] = field(default_factory=list)
    glossary_terms_matched: list[str] = field(default_factory=list)
    error: str | None = None


@dataclass
class ConsistencyResult:
    """一致性评审结果（语言对）"""

    source_key: str
    source_text: str
    review_model: ModelType
    lang_pair: tuple[str, str]  # (lang1, lang2)
    passed: bool
    feedback: str
    checked_terms_count: int = 0
    inconsistent_terms_count: int = 0
    error: str | None = None


@dataclass
class AgentWorkflowMetrics:
    """Agent 工作流指标（按翻译模型+评审模型+目标语言）"""

    model: ModelType  # 翻译模型
    review_model: ModelType  # 评审模型
    target_lang: str
    total_translations: int = 0
    avg_latency_ms: float = 0.0
    avg_quality_score: float = 0.0
    quality_pass_rate: float = 0.0
    retry_rate: float = 0.0
    error_count: int = 0


@dataclass
class ConsistencyMetrics:
    """一致性评审指标（按语言对）"""

    review_model: ModelType
    lang_pair: tuple[str, str]
    total_reviews: int = 0
    pass_rate: float = 0.0
    avg_checked_terms: float = 0.0
    avg_inconsistent_terms: float = 0.0
    error_count: int = 0


class SourceTextLoader:
    """源文本加载器"""

    def __init__(self, source_path: Path):
        self.source_path = source_path
        self.texts: dict[str, str] = {}

    def load(self, max_entries: int | None = None) -> dict[str, str]:
        """加载源文本，展平嵌套 JSON"""
        if not self.source_path.exists():
            raise FileNotFoundError(f"Source file not found: {self.source_path}")

        with open(self.source_path, encoding="utf-8") as f:
            data = json.load(f)

        self._flatten_json(data, "")

        if max_entries:
            keys = list(self.texts.keys())[:max_entries]
            self.texts = {k: self.texts[k] for k in keys}

        return self.texts

    def _flatten_json(self, obj: Any, prefix: str) -> None:
        """递归展平 JSON"""
        if isinstance(obj, dict):
            for key, value in obj.items():
                new_key = f"{prefix}.{key}" if prefix else key
                self._flatten_json(value, new_key)
        elif isinstance(obj, str):
            self.texts[prefix] = obj


class AgentAblationExperiment:
    """Agent 消融实验主类 - 按语言维度批处理"""

    def __init__(
        self,
        glossary_path: Path = GLOSSARY_PATH,
        source_path: Path = SOURCE_PATH,
        output_dir: Path = OUTPUT_DIR,
        max_glossary_entries: int = 500,
        max_source_entries: int = 10,
        target_languages: list[str] | None = None,
        models: list[ModelType] | None = None,
        review_models: list[ModelType] | None = None,
        quality_threshold: int = QUALITY_THRESHOLD,
        max_retries: int = 1,
        batch_size: int = 5,
        skip_review: bool = False,
    ):
        """
        初始化消融实验

        Args:
            glossary_path: 术语表路径
            source_path: 源文本路径
            output_dir: 输出目录
            max_glossary_entries: 最大术语表条目数
            max_source_entries: 最大源文本条目数
            target_languages: 目标语言列表
            models: 翻译测试模型列表
            review_models: 评审模型列表；为 None 时使用默认评审模型
            quality_threshold: 质量阈值
            max_retries: 最大重试次数
            batch_size: 批量翻译大小（每个语言每批处理的文本数）
            skip_review: 是否跳过质量评审（加速测试）
        """
        self.glossary_path = glossary_path
        self.source_loader = SourceTextLoader(source_path)
        self.output_dir = output_dir
        self.max_glossary_entries = max_glossary_entries
        self.max_source_entries = max_source_entries
        self.target_languages = target_languages or DEFAULT_TARGET_LANGUAGES
        self.models = models or list(ModelType)
        self.review_models = review_models or DEFAULT_REVIEW_MODELS
        self.quality_threshold = quality_threshold
        self.max_retries = max_retries
        self.batch_size = batch_size
        self.skip_review = skip_review

        self.glossary: Glossary | None = None
        # 翻译结果按 (source_key, model, review_model, target_lang) 索引
        self.results: list[AgentTranslationResult] = []
        # 一致性评审结果
        self.consistency_results: list[ConsistencyResult] = []
        # 共享 LLM 客户端
        self._llm_client: UnifiedLLMClient | None = None

    def setup(self) -> None:
        """初始化实验"""
        # 加载术语表
        if self.glossary_path.exists():
            self.glossary = glossary_service.load_glossary(
                self.glossary_path, max_entries=self.max_glossary_entries
            )
            print(f"[setup] 加载术语表完成，共 {len(self.glossary.terms)} 条")
        else:
            self.glossary = Glossary()
            print("[setup] 术语表文件不存在，使用空术语表")

        # 加载源文本
        self.source_loader.load(max_entries=self.max_source_entries)
        print(f"[setup] 加载源文本完成，共 {len(self.source_loader.texts)} 条")

        # 创建输出目录
        self.output_dir.mkdir(parents=True, exist_ok=True)
        print(f"[setup] 批量大小: {self.batch_size}")
        print(f"[setup] 翻译模型: {[m.value for m in self.models]}")
        print(f"[setup] 评审模型: {[m.value for m in self.review_models]}")
        print(f"[setup] 目标语言: {self.target_languages}")

        # 计算有效组合数（排除翻译和评审使用同一模型）
        valid_combo_count = sum(
            1 for t in self.models for r in self.review_models if t != r
        )
        print(f"[setup] 有效模型组合数: {valid_combo_count} (排除同模型组合)")

    async def _get_llm_client(self) -> UnifiedLLMClient:
        """获取或创建共享 LLM 客户端"""
        if self._llm_client is None:
            self._llm_client = UnifiedLLMClient()
        return self._llm_client

    async def _close_llm_client(self) -> None:
        """关闭 LLM 客户端"""
        if self._llm_client is not None:
            await self._llm_client.close()
            self._llm_client = None

    async def _translate_single(
        self,
        source_key: str,
        source_text: str,
        target_lang: str,
        translation_model: ModelType,
        feedback: ReviewFeedback | None = None,
    ) -> tuple[str, TranslationItem]:
        """
        翻译单个 (source_text, target_lang) 对

        Returns:
            (source_key, TranslationItem)
        """
        llm_client = await self._get_llm_client()
        agent = TranslationAgent(
            target_lang=target_lang,
            glossary=self.glossary,
            model=translation_model.value,
            llm_client=llm_client,
        )
        item = await agent.run(source_text, feedback)
        return source_key, item

    async def _translate_batch_for_language(
        self,
        batch_items: list[tuple[str, str]],
        target_lang: str,
        translation_model: ModelType,
        feedbacks: dict[str, ReviewFeedback] | None = None,
    ) -> list[tuple[str, TranslationItem]]:
        """
        为单个目标语言批量翻译多个源文本

        Args:
            batch_items: [(source_key, source_text), ...]
            target_lang: 单个目标语言
            translation_model: 翻译模型
            feedbacks: 评审反馈 {source_key: feedback}

        Returns:
            [(source_key, TranslationItem), ...]
        """
        feedbacks = feedbacks or {}
        tasks = [
            self._translate_single(
                key, text, target_lang, translation_model, feedbacks.get(key)
            )
            for key, text in batch_items
        ]

        results = await asyncio.gather(*tasks, return_exceptions=True)

        output = []
        for idx, result in enumerate(results):
            key, text = batch_items[idx]
            if isinstance(result, Exception):
                output.append((
                    key,
                    TranslationItem(
                        target_lang=target_lang,
                        translated_text=f"[ERROR: {result}]",
                        latency_ms=0,
                    ),
                ))
            else:
                output.append(result)
        return output

    async def _review_quality_single(
        self,
        source_key: str,
        source_text: str,
        translated_text: str,
        target_lang: str,
        review_model: ModelType,
    ) -> tuple[str, bool, int, str, list[str]]:
        """
        单个翻译的质量评审

        Returns:
            (source_key, passed, score, feedback, suggestions)
        """
        llm_client = await self._get_llm_client()
        agent = QualityReviewAgent(
            quality_threshold=self.quality_threshold,
            model=review_model.value,
            llm_client=llm_client,
        )
        result = await agent.run(source_text, translated_text, target_lang)
        return (
            source_key,
            result.passed,
            result.score.score,
            result.feedback,
            result.suggestions,
        )

    async def _review_quality_batch_for_language(
        self,
        items: list[tuple[str, str, str]],  # [(source_key, source_text, translated_text), ...]
        target_lang: str,
        review_model: ModelType,
    ) -> dict[str, tuple[bool, int, str, list[str]]]:
        """
        为单个目标语言批量质量评审

        Returns:
            {source_key: (passed, score, feedback, suggestions)}
        """
        tasks = [
            self._review_quality_single(key, src, trans, target_lang, review_model)
            for key, src, trans in items
        ]

        results = await asyncio.gather(*tasks, return_exceptions=True)

        output = {}
        for idx, result in enumerate(results):
            key = items[idx][0]
            if isinstance(result, Exception):
                output[key] = (True, 70, f"Review failed: {result}", [])
            else:
                _, passed, score, feedback, suggestions = result
                output[key] = (passed, score, feedback, suggestions)
        return output

    async def _review_consistency_for_pair(
        self,
        source_key: str,
        source_text: str,
        translations: list[TranslationItem],
        review_model: ModelType,
    ) -> ConsistencyResult:
        """
        对单个源文本的两种语言翻译进行一致性评审

        Args:
            translations: 包含两种语言的翻译结果
        """
        if len(translations) != 2:
            return ConsistencyResult(
                source_key=source_key,
                source_text=source_text,
                review_model=review_model,
                lang_pair=(translations[0].target_lang, translations[1].target_lang if len(translations) > 1 else ""),
                passed=True,
                feedback="Invalid number of translations for consistency review",
                error="Need exactly 2 translations",
            )

        llm_client = await self._get_llm_client()
        agent = ConsistencyReviewAgent(
            glossary=self.glossary,
            model=review_model.value,
            llm_client=llm_client,
        )

        try:
            result = await agent.run(source_text, translations)
            return ConsistencyResult(
                source_key=source_key,
                source_text=source_text,
                review_model=review_model,
                lang_pair=(translations[0].target_lang, translations[1].target_lang),
                passed=result.passed,
                feedback=result.feedback,
                checked_terms_count=result.checked_terms_count,
                inconsistent_terms_count=result.inconsistent_terms_count,
            )
        except Exception as e:
            return ConsistencyResult(
                source_key=source_key,
                source_text=source_text,
                review_model=review_model,
                lang_pair=(translations[0].target_lang, translations[1].target_lang),
                passed=True,
                feedback=f"Consistency review failed: {e}",
                error=str(e),
            )

    async def _review_consistency_batch_for_pair(
        self,
        items: list[tuple[str, str, TranslationItem, TranslationItem]],
        review_model: ModelType,
    ) -> list[ConsistencyResult]:
        """
        批量对语言对进行一致性评审

        Args:
            items: [(source_key, source_text, trans_lang1, trans_lang2), ...]
        """
        tasks = [
            self._review_consistency_for_pair(key, text, [t1, t2], review_model)
            for key, text, t1, t2 in items
        ]

        results = await asyncio.gather(*tasks, return_exceptions=True)

        output = []
        for idx, result in enumerate(results):
            if isinstance(result, Exception):
                key, text, t1, t2 = items[idx]
                output.append(ConsistencyResult(
                    source_key=key,
                    source_text=text,
                    review_model=review_model,
                    lang_pair=(t1.target_lang, t2.target_lang),
                    passed=True,
                    feedback=f"Consistency review failed: {result}",
                    error=str(result),
                ))
            else:
                output.append(result)
        return output

    async def run_experiment(self) -> dict[str, Any]:
        """
        运行完整实验

        批处理逻辑（以 100 文本、4 种语言、batch_size=20 为例）：
        - 翻译阶段：每种语言 5 轮（100/20），共 20 轮
        - 质量评审：每种语言 5 轮，共 20 轮
        - 一致性评审：语言循环组合 4 种 (1,2), (2,3), (3,4), (4,1)，每种 5 轮，共 20 轮
        """
        self.setup()

        all_metrics: list[AgentWorkflowMetrics] = []
        all_consistency_metrics: list[ConsistencyMetrics] = []
        items = list(self.source_loader.texts.items())

        # 构建有效的模型组合（排除翻译和评审使用同一模型的情况）
        valid_combinations = [
            (trans, rev)
            for trans in self.models
            for rev in self.review_models
            if trans != rev
        ]

        if not valid_combinations:
            raise ValueError(
                "没有有效的模型组合。翻译模型和评审模型不能相同，"
                "请确保 --models 和 --review-models 包含不同的模型。"
            )

        # 计算批次信息
        total_batches_per_lang = (len(items) + self.batch_size - 1) // self.batch_size
        # 循环组合: (1,2), (2,3), ..., (n-1,n), (n,1)
        langs = self.target_languages
        lang_pairs = [
            (langs[i], langs[(i + 1) % len(langs)])
            for i in range(len(langs))
        ]

        print(f"[experiment] 有效模型组合数: {len(valid_combinations)}")
        print(f"[experiment] 源文本数: {len(items)}")
        print(f"[experiment] 目标语言数: {len(self.target_languages)}")
        print(f"[experiment] 每语言批次数: {total_batches_per_lang}")
        print(f"[experiment] 语言对数（一致性评审）: {len(lang_pairs)}")

        try:
            combination_idx = 0
            combination_durations: dict[str, float] = {}  # 存储每个组合的耗时
            for translation_model, review_model in valid_combinations:
                combination_idx += 1
                combo_start_time = time.time()
                print(
                    f"\n{'='*60}\n"
                    f"[experiment] 组合 {combination_idx}/{len(valid_combinations)}: "
                    f"翻译={translation_model.value}, 评审={review_model.value}\n"
                    f"{'='*60}"
                )

                # 存储当前组合的翻译结果 {(source_key, target_lang): TranslationItem}
                translations_cache: dict[tuple[str, str], TranslationItem] = {}

                # ===== Phase 1: 翻译阶段（按语言批处理）=====
                print("\n[Phase 1] 翻译阶段")
                for target_lang in self.target_languages:
                    lang_name = get_language_name(target_lang, chinese=True)
                    print(f"  [{lang_name}] 开始翻译...")

                    for batch_idx in range(0, len(items), self.batch_size):
                        batch = items[batch_idx : batch_idx + self.batch_size]
                        batch_num = batch_idx // self.batch_size + 1

                        print(
                            f"    [batch {batch_num}/{total_batches_per_lang}] "
                            f"翻译 {len(batch)} 条文本"
                        )

                        batch_results = await self._translate_batch_for_language(
                            batch, target_lang, translation_model
                        )

                        # 缓存翻译结果
                        for source_key, item in batch_results:
                            translations_cache[(source_key, target_lang)] = item

                        # 批次间延迟
                        if batch_idx + self.batch_size < len(items):
                            await asyncio.sleep(0.5)

                    print(f"  [{lang_name}] 翻译完成")

                # ===== Phase 2: 质量评审阶段（按语言批处理）=====
                if not self.skip_review:
                    print("\n[Phase 2] 质量评审阶段")
                    for target_lang in self.target_languages:
                        lang_name = get_language_name(target_lang, chinese=True)
                        print(f"  [{lang_name}] 开始质量评审...")

                        for batch_idx in range(0, len(items), self.batch_size):
                            batch = items[batch_idx : batch_idx + self.batch_size]
                            batch_num = batch_idx // self.batch_size + 1

                            # 构建评审输入
                            review_items = []
                            for source_key, source_text in batch:
                                trans_item = translations_cache.get((source_key, target_lang))
                                if trans_item and not trans_item.translated_text.startswith("[ERROR"):
                                    review_items.append((
                                        source_key,
                                        source_text,
                                        trans_item.translated_text,
                                    ))

                            if not review_items:
                                continue

                            print(
                                f"    [batch {batch_num}/{total_batches_per_lang}] "
                                f"评审 {len(review_items)} 条翻译"
                            )

                            review_results = await self._review_quality_batch_for_language(
                                review_items, target_lang, review_model
                            )

                            # 更新翻译结果的质量信息
                            for source_key, (_, score, feedback, _) in review_results.items():
                                trans_item = translations_cache.get((source_key, target_lang))
                                if trans_item:
                                    trans_item.quality_score = score
                                    trans_item.quality_feedback = feedback

                            # 批次间延迟
                            if batch_idx + self.batch_size < len(items):
                                await asyncio.sleep(0.5)

                        print(f"  [{lang_name}] 质量评审完成")

                # ===== Phase 3: 收集翻译结果 =====
                for (source_key, target_lang), trans_item in translations_cache.items():
                    source_text = self.source_loader.texts.get(source_key, "")
                    self.results.append(AgentTranslationResult(
                        source_key=source_key,
                        source_text=source_text,
                        model=translation_model,
                        review_model=review_model,
                        target_lang=target_lang,
                        translated_text=trans_item.translated_text,
                        quality_score=trans_item.quality_score,
                        quality_feedback=trans_item.quality_feedback,
                        latency_ms=trans_item.latency_ms,
                        retry_count=trans_item.retry_count,
                        glossary_terms_found=trans_item.glossary_terms_found,
                        glossary_terms_matched=trans_item.glossary_terms_matched,
                        error=None if not trans_item.translated_text.startswith("[ERROR") else trans_item.translated_text,
                    ))

                # ===== Phase 4: 一致性评审阶段（按语言对批处理）=====
                if not self.skip_review and len(self.target_languages) > 1:
                    print(f"\n[Phase 3] 一致性评审阶段（{len(lang_pairs)} 个语言对）")

                    for lang1, lang2 in lang_pairs:
                        lang1_name = get_language_name(lang1, chinese=True)
                        lang2_name = get_language_name(lang2, chinese=True)
                        print(f"  [{lang1_name} <-> {lang2_name}] 开始一致性评审...")

                        for batch_idx in range(0, len(items), self.batch_size):
                            batch = items[batch_idx : batch_idx + self.batch_size]
                            batch_num = batch_idx // self.batch_size + 1

                            # 构建一致性评审输入
                            consistency_items = []
                            for source_key, source_text in batch:
                                trans1 = translations_cache.get((source_key, lang1))
                                trans2 = translations_cache.get((source_key, lang2))
                                if (
                                    trans1 and trans2
                                    and not trans1.translated_text.startswith("[ERROR")
                                    and not trans2.translated_text.startswith("[ERROR")
                                ):
                                    consistency_items.append((source_key, source_text, trans1, trans2))

                            if not consistency_items:
                                continue

                            print(
                                f"    [batch {batch_num}/{total_batches_per_lang}] "
                                f"评审 {len(consistency_items)} 条"
                            )

                            consistency_results = await self._review_consistency_batch_for_pair(
                                consistency_items, review_model
                            )
                            self.consistency_results.extend(consistency_results)

                            # 批次间延迟
                            if batch_idx + self.batch_size < len(items):
                                await asyncio.sleep(0.5)

                        print(f"  [{lang1_name} <-> {lang2_name}] 一致性评审完成")

                # 计算该模型组合的指标
                print("\n[stats] 模型组合指标统计:")
                for target_lang in self.target_languages:
                    metrics = self._calculate_metrics(translation_model, review_model, target_lang)
                    all_metrics.append(metrics)

                    print(
                        f"  [{get_language_name(target_lang, chinese=True)}] "
                        f"平均质量: {metrics.avg_quality_score:.1f}, "
                        f"通过率: {metrics.quality_pass_rate:.2%}, "
                        f"平均延迟: {metrics.avg_latency_ms:.0f}ms, "
                        f"错误: {metrics.error_count}"
                    )

                # 计算一致性指标
                for lang_pair in lang_pairs:
                    consistency_metrics = self._calculate_consistency_metrics(review_model, lang_pair)
                    all_consistency_metrics.append(consistency_metrics)

                # 计算并记录当前模型组合的总耗时
                combo_duration = time.time() - combo_start_time
                combo_key = f"{translation_model.value}+{review_model.value}"
                combination_durations[combo_key] = combo_duration
                print(
                    f"\n[timing] 组合 {combo_key} 总耗时: {combo_duration:.1f}s "
                    f"({combo_duration/60:.1f}min)"
                )

        finally:
            await self._close_llm_client()

        # 生成报告
        report = self._generate_report(all_metrics, all_consistency_metrics, combination_durations)
        self._save_results(report)

        return report

    def _calculate_metrics(
        self, model: ModelType, review_model: ModelType, target_lang: str
    ) -> AgentWorkflowMetrics:
        """计算指定模型和语言的评估指标"""
        filtered = [
            r
            for r in self.results
            if r.model == model and r.review_model == review_model and r.target_lang == target_lang
        ]

        if not filtered:
            return AgentWorkflowMetrics(model=model, review_model=review_model, target_lang=target_lang)

        # 计算各项指标
        valid_results = [r for r in filtered if r.error is None]
        latencies = [r.latency_ms for r in valid_results]
        quality_scores = [r.quality_score for r in valid_results if r.quality_score]

        avg_latency = sum(latencies) / len(latencies) if latencies else 0
        avg_quality = sum(quality_scores) / len(quality_scores) if quality_scores else 0

        passed_count = sum(
            1 for r in valid_results
            if r.quality_score and r.quality_score >= self.quality_threshold
        )
        quality_pass_rate = passed_count / len(valid_results) if valid_results else 0

        retry_count = sum(1 for r in valid_results if r.retry_count > 0)
        retry_rate = retry_count / len(valid_results) if valid_results else 0

        error_count = sum(1 for r in filtered if r.error is not None)

        return AgentWorkflowMetrics(
            model=model,
            review_model=review_model,
            target_lang=target_lang,
            total_translations=len(filtered),
            avg_latency_ms=avg_latency,
            avg_quality_score=avg_quality,
            quality_pass_rate=quality_pass_rate,
            retry_rate=retry_rate,
            error_count=error_count,
        )

    def _calculate_consistency_metrics(
        self, review_model: ModelType, lang_pair: tuple[str, str]
    ) -> ConsistencyMetrics:
        """计算指定评审模型和语言对的一致性指标"""
        filtered = [
            r
            for r in self.consistency_results
            if r.review_model == review_model and r.lang_pair == lang_pair
        ]

        if not filtered:
            return ConsistencyMetrics(review_model=review_model, lang_pair=lang_pair)

        valid_results = [r for r in filtered if r.error is None]
        passed_count = sum(1 for r in valid_results if r.passed)
        pass_rate = passed_count / len(valid_results) if valid_results else 0

        checked_terms = [r.checked_terms_count for r in valid_results]
        inconsistent_terms = [r.inconsistent_terms_count for r in valid_results]

        avg_checked = sum(checked_terms) / len(checked_terms) if checked_terms else 0
        avg_inconsistent = sum(inconsistent_terms) / len(inconsistent_terms) if inconsistent_terms else 0

        error_count = sum(1 for r in filtered if r.error is not None)

        return ConsistencyMetrics(
            review_model=review_model,
            lang_pair=lang_pair,
            total_reviews=len(filtered),
            pass_rate=pass_rate,
            avg_checked_terms=avg_checked,
            avg_inconsistent_terms=avg_inconsistent,
            error_count=error_count,
        )

    def _generate_report(
        self,
        metrics: list[AgentWorkflowMetrics],
        consistency_metrics: list[ConsistencyMetrics] | None = None,
        combination_durations: dict[str, float] | None = None,
    ) -> dict[str, Any]:
        """生成实验报告"""
        consistency_metrics = consistency_metrics or []
        combination_durations = combination_durations or {}
        # 循环组合: (1,2), (2,3), ..., (n-1,n), (n,1)
        langs = self.target_languages
        lang_pairs = [
            (langs[i], langs[(i + 1) % len(langs)])
            for i in range(len(langs))
        ]

        report = {
            "experiment_info": {
                "translation_models": [m.value for m in self.models],
                "review_models": [m.value for m in self.review_models],
                "target_languages": self.target_languages,
                "language_pairs": [f"{p[0]}<->{p[1]}" for p in lang_pairs],
                "source_entries": len(self.source_loader.texts),
                "glossary_entries": len(self.glossary.terms) if self.glossary else 0,
                "quality_threshold": self.quality_threshold,
                "max_retries": self.max_retries,
                "batch_size": self.batch_size,
                "skip_review": self.skip_review,
            },
            "metrics_by_model_combination": {},  # 按翻译+评审模型组合
            "metrics_by_translation_model": {},  # 按翻译模型汇总
            "metrics_by_review_model": {},  # 按评审模型汇总
            "metrics_by_language": {},
            "consistency_by_language_pair": {},  # 按语言对的一致性指标
            "summary": {},
        }

        # 按翻译+评审模型组合汇总（排除同模型组合）
        for trans_model in self.models:
            for rev_model in self.review_models:
                if trans_model == rev_model:
                    continue  # 跳过翻译和评审使用同一模型的组合
                combo_key = f"{trans_model.value}+{rev_model.value}"
                combo_metrics = [
                    m for m in metrics
                    if m.model == trans_model and m.review_model == rev_model
                ]
                if combo_metrics:
                    combo_duration = combination_durations.get(combo_key, 0.0)
                    report["metrics_by_model_combination"][combo_key] = {
                        "translation_model": trans_model.value,
                        "review_model": rev_model.value,
                        "total_duration_seconds": combo_duration,
                        "total_duration_minutes": combo_duration / 60,
                        "avg_latency_ms": (
                            sum(m.avg_latency_ms for m in combo_metrics) / len(combo_metrics)
                        ),
                        "avg_quality_score": (
                            sum(m.avg_quality_score for m in combo_metrics)
                            / len(combo_metrics)
                        ),
                        "quality_pass_rate": (
                            sum(m.quality_pass_rate for m in combo_metrics)
                            / len(combo_metrics)
                        ),
                        "retry_rate": (
                            sum(m.retry_rate for m in combo_metrics) / len(combo_metrics)
                        ),
                        "total_errors": sum(m.error_count for m in combo_metrics),
                    }

        # 按翻译模型汇总（跨所有评审模型）
        for model in self.models:
            model_metrics = [m for m in metrics if m.model == model]
            if model_metrics:
                report["metrics_by_translation_model"][model.value] = {
                    "avg_latency_ms": (
                        sum(m.avg_latency_ms for m in model_metrics) / len(model_metrics)
                    ),
                    "avg_quality_score": (
                        sum(m.avg_quality_score for m in model_metrics)
                        / len(model_metrics)
                    ),
                    "quality_pass_rate": (
                        sum(m.quality_pass_rate for m in model_metrics)
                        / len(model_metrics)
                    ),
                    "retry_rate": (
                        sum(m.retry_rate for m in model_metrics) / len(model_metrics)
                    ),
                    "total_errors": sum(m.error_count for m in model_metrics),
                }

        # 按评审模型汇总（跨所有翻译模型）
        for model in self.review_models:
            model_metrics = [m for m in metrics if m.review_model == model]
            if model_metrics:
                report["metrics_by_review_model"][model.value] = {
                    "avg_latency_ms": (
                        sum(m.avg_latency_ms for m in model_metrics) / len(model_metrics)
                    ),
                    "avg_quality_score": (
                        sum(m.avg_quality_score for m in model_metrics)
                        / len(model_metrics)
                    ),
                    "quality_pass_rate": (
                        sum(m.quality_pass_rate for m in model_metrics)
                        / len(model_metrics)
                    ),
                    "retry_rate": (
                        sum(m.retry_rate for m in model_metrics) / len(model_metrics)
                    ),
                    "total_errors": sum(m.error_count for m in model_metrics),
                }

        # 按语言汇总
        for lang in self.target_languages:
            lang_metrics = [m for m in metrics if m.target_lang == lang]
            if lang_metrics:
                report["metrics_by_language"][lang] = {
                    "language_name": get_language_name(lang, chinese=True),
                    "avg_latency_ms": (
                        sum(m.avg_latency_ms for m in lang_metrics) / len(lang_metrics)
                    ),
                    "avg_quality_score": (
                        sum(m.avg_quality_score for m in lang_metrics)
                        / len(lang_metrics)
                    ),
                    "quality_pass_rate": (
                        sum(m.quality_pass_rate for m in lang_metrics)
                        / len(lang_metrics)
                    ),
                }

        # 按语言对汇总一致性指标
        for lang_pair in lang_pairs:
            pair_key = f"{lang_pair[0]}<->{lang_pair[1]}"
            pair_metrics = [
                m for m in consistency_metrics
                if m.lang_pair == lang_pair
            ]
            if pair_metrics:
                report["consistency_by_language_pair"][pair_key] = {
                    "lang1": lang_pair[0],
                    "lang1_name": get_language_name(lang_pair[0], chinese=True),
                    "lang2": lang_pair[1],
                    "lang2_name": get_language_name(lang_pair[1], chinese=True),
                    "total_reviews": sum(m.total_reviews for m in pair_metrics),
                    "avg_pass_rate": (
                        sum(m.pass_rate for m in pair_metrics) / len(pair_metrics)
                    ),
                    "avg_checked_terms": (
                        sum(m.avg_checked_terms for m in pair_metrics) / len(pair_metrics)
                    ),
                    "avg_inconsistent_terms": (
                        sum(m.avg_inconsistent_terms for m in pair_metrics) / len(pair_metrics)
                    ),
                    "total_errors": sum(m.error_count for m in pair_metrics),
                }

        # 总体汇总
        if metrics:
            consistency_pass_rate = 0.0
            if consistency_metrics:
                consistency_pass_rate = (
                    sum(m.pass_rate for m in consistency_metrics) / len(consistency_metrics)
                )

            total_experiment_duration = sum(combination_durations.values())
            report["summary"] = {
                "total_translations": sum(m.total_translations for m in metrics),
                "total_experiment_duration_seconds": total_experiment_duration,
                "total_experiment_duration_minutes": total_experiment_duration / 60,
                "overall_avg_latency_ms": (
                    sum(m.avg_latency_ms for m in metrics) / len(metrics)
                ),
                "overall_avg_quality_score": (
                    sum(m.avg_quality_score for m in metrics) / len(metrics)
                ),
                "overall_quality_pass_rate": (
                    sum(m.quality_pass_rate for m in metrics) / len(metrics)
                ),
                "overall_consistency_pass_rate": consistency_pass_rate,
                "total_consistency_reviews": sum(m.total_reviews for m in consistency_metrics),
                "total_errors": sum(m.error_count for m in metrics),
            }

        return report

    def _save_results(self, report: dict[str, Any]) -> None:
        """保存结果"""
        timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")

        # 保存报告 JSON
        report_path = self.output_dir / f"agent_ablation_report_{timestamp}.json"
        with open(report_path, "w", encoding="utf-8") as f:
            json.dump(report, f, ensure_ascii=False, indent=2)
        print(f"\n[save] 报告已保存: {report_path}")

        # 保存翻译详细结果 JSON
        results_path = self.output_dir / f"agent_ablation_results_{timestamp}.json"
        results_data = [
            {
                "source_key": r.source_key,
                "source_text": r.source_text,
                "translation_model": r.model.value,
                "review_model": r.review_model.value,
                "target_lang": r.target_lang,
                "target_lang_name": get_language_name(r.target_lang, chinese=True),
                "translated_text": r.translated_text,
                "quality_score": r.quality_score,
                "quality_feedback": r.quality_feedback,
                "latency_ms": r.latency_ms,
                "retry_count": r.retry_count,
                "glossary_terms_found": r.glossary_terms_found,
                "glossary_terms_matched": r.glossary_terms_matched,
                "error": r.error,
            }
            for r in self.results
        ]
        with open(results_path, "w", encoding="utf-8") as f:
            json.dump(results_data, f, ensure_ascii=False, indent=2)
        print(f"[save] 翻译详细结果已保存: {results_path}")

        # 保存一致性评审结果 JSON
        if self.consistency_results:
            consistency_path = self.output_dir / f"agent_ablation_consistency_{timestamp}.json"
            consistency_data = [
                {
                    "source_key": r.source_key,
                    "source_text": r.source_text,
                    "review_model": r.review_model.value,
                    "lang1": r.lang_pair[0],
                    "lang1_name": get_language_name(r.lang_pair[0], chinese=True),
                    "lang2": r.lang_pair[1],
                    "lang2_name": get_language_name(r.lang_pair[1], chinese=True),
                    "passed": r.passed,
                    "feedback": r.feedback,
                    "checked_terms_count": r.checked_terms_count,
                    "inconsistent_terms_count": r.inconsistent_terms_count,
                    "error": r.error,
                }
                for r in self.consistency_results
            ]
            with open(consistency_path, "w", encoding="utf-8") as f:
                json.dump(consistency_data, f, ensure_ascii=False, indent=2)
            print(f"[save] 一致性评审结果已保存: {consistency_path}")

        # 保存模型比较 CSV
        self._save_comparison_csv(timestamp)

        # 保存一致性汇总 CSV
        if self.consistency_results:
            self._save_consistency_summary_csv(timestamp)

    def _save_consistency_summary_csv(self, timestamp: str) -> None:
        """保存一致性评审汇总 CSV"""
        # 循环组合: (1,2), (2,3), ..., (n-1,n), (n,1)
        langs = self.target_languages
        lang_pairs = [
            (langs[i], langs[(i + 1) % len(langs)])
            for i in range(len(langs))
        ]

        headers = [
            "review_model",
            "lang1",
            "lang1_name",
            "lang2",
            "lang2_name",
            "total_reviews",
            "pass_rate",
            "avg_checked_terms",
            "avg_inconsistent_terms",
            "error_count",
        ]

        rows = []
        for rev_model in self.review_models:
            for lang_pair in lang_pairs:
                metrics = self._calculate_consistency_metrics(rev_model, lang_pair)
                rows.append({
                    "review_model": rev_model.value,
                    "lang1": lang_pair[0],
                    "lang1_name": get_language_name(lang_pair[0], chinese=True),
                    "lang2": lang_pair[1],
                    "lang2_name": get_language_name(lang_pair[1], chinese=True),
                    "total_reviews": metrics.total_reviews,
                    "pass_rate": f"{metrics.pass_rate:.2%}",
                    "avg_checked_terms": f"{metrics.avg_checked_terms:.1f}",
                    "avg_inconsistent_terms": f"{metrics.avg_inconsistent_terms:.1f}",
                    "error_count": metrics.error_count,
                })

        csv_path = self.output_dir / f"agent_ablation_consistency_summary_{timestamp}.csv"
        with open(csv_path, "w", encoding="utf-8-sig", newline="") as f:
            writer = csv.DictWriter(f, fieldnames=headers)
            writer.writeheader()
            writer.writerows(rows)
        print(f"[save] 一致性汇总 CSV 已保存: {csv_path}")

    def _save_comparison_csv(self, timestamp: str) -> None:
        """保存模型比较 CSV，方便横向对比不同模型组合的翻译结果"""
        # 构建有效的模型组合（翻译模型+评审模型，排除同模型组合）
        model_combinations = [
            (trans.value, rev.value)
            for trans in self.models
            for rev in self.review_models
            if trans != rev
        ]

        if not model_combinations:
            print("[save] 没有有效的模型组合，跳过比较 CSV")
            return

        # 按 (source_key, target_lang) 分组结果，使用 (翻译模型, 评审模型) 作为二级 key
        grouped: dict[tuple[str, str], dict[tuple[str, str], AgentTranslationResult]] = {}
        for r in self.results:
            key = (r.source_key, r.target_lang)
            combo_key = (r.model.value, r.review_model.value)
            if key not in grouped:
                grouped[key] = {}
            grouped[key][combo_key] = r

        # 构建 CSV 表头（翻译结果放在一起、质量评分放在一起、延迟放在一起）
        headers = [
            "source_key",
            "target_lang",
            "target_lang_name",
            "source_text",
        ]
        # 所有模型组合的翻译结果列
        for trans, rev in model_combinations:
            combo_name = f"{trans}+{rev}"
            headers.append(f"{combo_name}_translation")
        # 所有模型组合的质量评分列
        for trans, rev in model_combinations:
            combo_name = f"{trans}+{rev}"
            headers.append(f"{combo_name}_quality_score")
        # 所有模型组合的延迟列
        for trans, rev in model_combinations:
            combo_name = f"{trans}+{rev}"
            headers.append(f"{combo_name}_latency_ms")

        # 构建 CSV 行
        rows = []
        for (source_key, target_lang), combo_results in sorted(grouped.items()):
            # 获取源文本
            source_text = ""
            for r in combo_results.values():
                source_text = r.source_text
                break

            row = {
                "source_key": source_key,
                "target_lang": target_lang,
                "target_lang_name": get_language_name(target_lang, chinese=True),
                "source_text": source_text,
            }

            for trans, rev in model_combinations:
                combo_key = (trans, rev)
                combo_name = f"{trans}+{rev}"
                result = combo_results.get(combo_key)
                if result:
                    row[f"{combo_name}_translation"] = result.translated_text
                    row[f"{combo_name}_quality_score"] = (
                        result.quality_score if result.quality_score else ""
                    )
                    row[f"{combo_name}_latency_ms"] = f"{result.latency_ms:.0f}"
                else:
                    row[f"{combo_name}_translation"] = ""
                    row[f"{combo_name}_quality_score"] = ""
                    row[f"{combo_name}_latency_ms"] = ""

            rows.append(row)

        # 写入 CSV
        csv_path = self.output_dir / f"agent_ablation_comparison_{timestamp}.csv"
        with open(csv_path, "w", encoding="utf-8-sig", newline="") as f:
            writer = csv.DictWriter(f, fieldnames=headers)
            writer.writeheader()
            writer.writerows(rows)
        print(f"[save] 模型比较 CSV 已保存: {csv_path}")

        # 保存质量评分汇总 CSV
        self._save_quality_summary_csv(timestamp)

    def _save_quality_summary_csv(self, timestamp: str) -> None:
        """保存质量评分汇总 CSV"""
        headers = [
            "translation_model",
            "review_model",
            "target_lang",
            "target_lang_name",
            "total_translations",
            "avg_quality_score",
            "quality_pass_rate",
            "avg_latency_ms",
            "retry_rate",
            "error_count",
        ]

        rows = []
        for trans_model in self.models:
            for rev_model in self.review_models:
                if trans_model == rev_model:
                    continue  # 跳过翻译和评审使用同一模型的组合
                for lang in self.target_languages:
                    metrics = self._calculate_metrics(trans_model, rev_model, lang)
                    rows.append({
                        "translation_model": trans_model.value,
                        "review_model": rev_model.value,
                        "target_lang": lang,
                        "target_lang_name": get_language_name(lang, chinese=True),
                        "total_translations": metrics.total_translations,
                        "avg_quality_score": f"{metrics.avg_quality_score:.1f}",
                        "quality_pass_rate": f"{metrics.quality_pass_rate:.2%}",
                        "avg_latency_ms": f"{metrics.avg_latency_ms:.0f}",
                        "retry_rate": f"{metrics.retry_rate:.2%}",
                        "error_count": metrics.error_count,
                    })

        csv_path = self.output_dir / f"agent_ablation_quality_summary_{timestamp}.csv"
        with open(csv_path, "w", encoding="utf-8-sig", newline="") as f:
            writer = csv.DictWriter(f, fieldnames=headers)
            writer.writeheader()
            writer.writerows(rows)
        print(f"[save] 质量汇总 CSV 已保存: {csv_path}")


# ============== Pytest 测试用例 ==============


class TestAgentAblation:
    """Agent 消融实验测试"""

    @pytest.mark.asyncio
    async def test_run_mini_experiment(self):
        """运行小规模消融实验"""
        if not GLOSSARY_PATH.exists() or not SOURCE_PATH.exists():
            pytest.skip("Data files not found")

        has_keys = (
            os.getenv("OPENAI_API_KEY")
            or os.getenv("ANTHROPIC_API_KEY")
            or os.getenv("GOOGLE_API_KEY")
        )
        if not has_keys:
            pytest.skip("No API keys configured")

        experiment = AgentAblationExperiment(
            max_glossary_entries=50,
            max_source_entries=2,
            target_languages=[LanguageCode.ZH_CN.value, LanguageCode.ZH_TW.value],
            models=[ModelType.CLAUDE_SONNET],  # 只测试一个翻译模型
            review_models=[ModelType.GPT_MINI],  # 评审模型（必须与翻译模型不同）
            quality_threshold=50,
            max_retries=0,
            batch_size=2,
        )

        report = await experiment.run_experiment()

        assert "experiment_info" in report
        assert "summary" in report
        assert report["summary"]["total_translations"] > 0

    @pytest.mark.asyncio
    async def test_single_language_translation(self):
        """测试单语言批量翻译"""
        if not GLOSSARY_PATH.exists():
            pytest.skip("Glossary file not found")

        if not os.getenv("ANTHROPIC_API_KEY"):
            pytest.skip("ANTHROPIC_API_KEY not set")

        glossary = glossary_service.load_glossary(GLOSSARY_PATH, max_entries=50)

        experiment = AgentAblationExperiment(
            max_glossary_entries=50,
            max_source_entries=2,
            target_languages=[LanguageCode.ZH_CN.value],
            models=[ModelType.CLAUDE_SONNET],
            review_models=[ModelType.GPT_MINI],
            batch_size=2,
            skip_review=True,  # 跳过评审加速测试
        )
        experiment.glossary = glossary

        # 测试单语言批量翻译
        batch_items = [
            ("test.hello", "Hello, world!"),
            ("test.welcome", "Welcome to our platform!"),
        ]

        results = await experiment._translate_batch_for_language(
            batch_items,
            LanguageCode.ZH_CN.value,
            ModelType.CLAUDE_SONNET,
        )

        assert len(results) == 2
        for _, item in results:
            assert item.translated_text
            assert not item.translated_text.startswith("[ERROR")
            assert item.target_lang == LanguageCode.ZH_CN.value


class TestAgentAblationComparison:
    """Agent 消融实验模型比较测试"""

    @pytest.mark.asyncio
    async def test_multi_model_comparison(self):
        """测试多模型比较"""
        if not GLOSSARY_PATH.exists() or not SOURCE_PATH.exists():
            pytest.skip("Data files not found")

        # 检查所有 API 密钥
        required_keys = [
            ("OPENAI_API_KEY", ModelType.GPT_MINI),
            ("ANTHROPIC_API_KEY", ModelType.CLAUDE_SONNET),
            ("GOOGLE_API_KEY", ModelType.GEMINI_FLASH),
        ]

        available_models = []
        for env_key, model in required_keys:
            if os.getenv(env_key):
                available_models.append(model)

        if len(available_models) < 2:
            pytest.skip("At least 2 API keys required for comparison test")

        # 确保翻译模型和评审模型不同
        translation_models = available_models[:1]  # 使用第一个作为翻译模型
        review_models = available_models[1:2]  # 使用第二个作为评审模型

        experiment = AgentAblationExperiment(
            max_glossary_entries=50,
            max_source_entries=2,
            target_languages=[LanguageCode.ZH_CN.value, LanguageCode.ZH_TW.value],
            models=translation_models,
            review_models=review_models,
            quality_threshold=50,
            max_retries=0,
            batch_size=2,
        )

        report = await experiment.run_experiment()

        assert len(report["metrics_by_translation_model"]) == len(translation_models)
        for model in translation_models:
            assert model.value in report["metrics_by_translation_model"]


# ============== 命令行入口 ==============


def _ignore_genai_aclose_error(
    loop: asyncio.AbstractEventLoop, context: dict[str, Any]
) -> None:
    """忽略 google-genai 库的 aclose 错误（已知问题）"""
    exception = context.get("exception")
    if exception and isinstance(exception, AttributeError):
        if "_async_httpx_client" in str(exception):
            return
    loop.default_exception_handler(context)


async def main():
    """命令行入口"""
    import argparse

    # 设置异常处理器
    loop = asyncio.get_running_loop()
    loop.set_exception_handler(_ignore_genai_aclose_error)

    parser = argparse.ArgumentParser(description="Agent 消融实验：模型翻译效果对比")
    parser.add_argument(
        "--max-glossary",
        type=int,
        default=100000,
        help="最大术语表条目数",
    )
    parser.add_argument(
        "--max-source",
        type=int,
        default=2000,
        help="最大源文本条目数",
    )
    parser.add_argument(
        "--languages",
        nargs="+",
        default=["zh-CN", "zh-TW", "ko-KR", "pt-BR"],
        help="目标语言列表",
    )
    parser.add_argument(
        "--models",
        nargs="+",
        choices=["gpt_mini", "gpt", "claude_sonnet", "claude_opus", "gemini_flash", "gemini_pro"],
        default=["gpt_mini", "claude_sonnet"],
        help="翻译测试模型列表",
    )
    parser.add_argument(
        "--review-models",
        nargs="+",
        choices=["gpt_mini", "gpt", "claude_sonnet", "claude_opus", "gemini_flash", "gemini_pro"],
        default=["claude_sonnet"],
        help="评审模型列表（可多选进行对比）",
    )
    parser.add_argument(
        "--quality-threshold",
        type=int,
        default=90,
        help="质量阈值 (0-100)",
    )
    parser.add_argument(
        "--max-retries",
        type=int,
        default=2,
        help="最大重试次数",
    )
    parser.add_argument(
        "--batch-size",
        type=int,
        default=20,
        help="批量翻译大小（并发数）",
    )
    parser.add_argument(
        "--skip-review",
        action="store_true",
        help="跳过质量评审（加速测试）",
    )

    args = parser.parse_args()

    # 解析模型
    model_mapping = {
        "gpt_mini": ModelType.GPT_MINI,
        "gpt": ModelType.GPT,
        "claude_sonnet": ModelType.CLAUDE_SONNET,
        "claude_opus": ModelType.CLAUDE_OPUS,
        "gemini_flash": ModelType.GEMINI_FLASH,
        "gemini_pro": ModelType.GEMINI_PRO,
    }
    selected_models = [model_mapping[m] for m in args.models]
    selected_review_models = [model_mapping[m] for m in args.review_models]

    experiment = AgentAblationExperiment(
        max_glossary_entries=args.max_glossary,
        max_source_entries=args.max_source,
        target_languages=args.languages,
        models=selected_models,
        review_models=selected_review_models,
        quality_threshold=args.quality_threshold,
        max_retries=args.max_retries,
        batch_size=args.batch_size,
        skip_review=args.skip_review,
    )

    report = await experiment.run_experiment()

    # 打印汇总
    print("\n" + "=" * 70)
    print("Agent 消融实验汇总（按语言维度批处理）")
    print("=" * 70)

    exp_info = report["experiment_info"]
    print(f"\n翻译模型: {exp_info['translation_models']}")
    print(f"评审模型: {exp_info['review_models']}")
    print(f"目标语言: {exp_info['target_languages']}")
    print(f"语言对（一致性评审）: {exp_info['language_pairs']}")

    # 按模型组合统计
    print("\n按模型组合统计 (翻译+评审):")
    for combo, metrics in report["metrics_by_model_combination"].items():
        print(f"\n  {combo}:")
        print(f"    总耗时: {metrics['total_duration_seconds']:.1f}s ({metrics['total_duration_minutes']:.1f}min)")
        print(f"    平均延迟: {metrics['avg_latency_ms']:.0f}ms")
        print(f"    平均质量评分: {metrics['avg_quality_score']:.1f}")
        print(f"    质量通过率: {metrics['quality_pass_rate']:.2%}")
        print(f"    重试率: {metrics['retry_rate']:.2%}")
        print(f"    错误数: {metrics['total_errors']}")

    # 按翻译模型汇总
    print("\n按翻译模型汇总:")
    for model, metrics in report["metrics_by_translation_model"].items():
        print(f"\n  {model}:")
        print(f"    平均延迟: {metrics['avg_latency_ms']:.0f}ms")
        print(f"    平均质量评分: {metrics['avg_quality_score']:.1f}")
        print(f"    质量通过率: {metrics['quality_pass_rate']:.2%}")
        print(f"    重试率: {metrics['retry_rate']:.2%}")
        print(f"    错误数: {metrics['total_errors']}")

    # 按评审模型汇总
    if len(exp_info["review_models"]) > 1:
        print("\n按评审模型汇总:")
        for model, metrics in report["metrics_by_review_model"].items():
            print(f"\n  {model}:")
            print(f"    平均质量评分: {metrics['avg_quality_score']:.1f}")
            print(f"    质量通过率: {metrics['quality_pass_rate']:.2%}")

    print("\n按语言统计:")
    for lang, metrics in report["metrics_by_language"].items():
        print(f"\n  {metrics['language_name']} ({lang}):")
        print(f"    平均延迟: {metrics['avg_latency_ms']:.0f}ms")
        print(f"    平均质量评分: {metrics['avg_quality_score']:.1f}")
        print(f"    质量通过率: {metrics['quality_pass_rate']:.2%}")

    # 按语言对统计一致性
    if report["consistency_by_language_pair"]:
        print("\n按语言对统计一致性:")
        for metrics in report["consistency_by_language_pair"].values():
            print(f"\n  {metrics['lang1_name']} <-> {metrics['lang2_name']}:")
            print(f"    总评审数: {metrics['total_reviews']}")
            print(f"    通过率: {metrics['avg_pass_rate']:.2%}")
            print(f"    平均检查术语数: {metrics['avg_checked_terms']:.1f}")
            print(f"    平均不一致术语数: {metrics['avg_inconsistent_terms']:.1f}")
            print(f"    错误数: {metrics['total_errors']}")

    print("\n总体汇总:")
    summary = report["summary"]
    print(f"  总翻译数: {summary['total_translations']}")
    print(f"  实验总耗时: {summary['total_experiment_duration_seconds']:.1f}s ({summary['total_experiment_duration_minutes']:.1f}min)")
    print(f"  平均延迟: {summary['overall_avg_latency_ms']:.0f}ms")
    print(f"  平均质量评分: {summary['overall_avg_quality_score']:.1f}")
    print(f"  质量通过率: {summary['overall_quality_pass_rate']:.2%}")
    print(f"  一致性通过率: {summary['overall_consistency_pass_rate']:.2%}")
    print(f"  总一致性评审数: {summary['total_consistency_reviews']}")
    print(f"  总错误数: {summary['total_errors']}")


if __name__ == "__main__":
    asyncio.run(main())
