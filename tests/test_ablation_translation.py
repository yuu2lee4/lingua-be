"""
消融实验：比较 GPT-5-mini, Claude Sonnet 4.5 和 Gemini 3 Flash 的翻译效果

测试目标：
1. 评估三个模型在多语言翻译任务中的表现
2. 检验术语表匹配准确性
3. 比较翻译质量指标
"""

import asyncio
import csv
import json
import os
import time
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Any

# 减少第三方库的日志噪音
import logging
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

# 配置路径
BASE_DIR = Path(__file__).parent.parent
DATA_DIR = BASE_DIR / "example"
GLOSSARY_PATH = DATA_DIR / "glossary.json"
SOURCE_PATH = DATA_DIR / "en.json"
OUTPUT_DIR = BASE_DIR / "tests" / "ablation_results"


class LanguageType(str, Enum):
    """支持的语言类型"""

    DE_DE = "de-DE"
    EN_US = "en-US"
    ES_ES = "es-ES"
    FR_FR = "fr-FR"
    JA_JP = "ja-JP"
    PT_BR = "pt-BR"
    RU_RU = "ru-RU"
    UK_UA = "uk-UA"
    VI_VN = "vi-VN"
    ZH_CN = "zh-CN"
    ZH_TW = "zh-TW"
    AR_AE = "ar-AE"
    NL_NL = "nl-NL"
    TR_TR = "tr-TR"
    KO_KR = "ko-KR"


# AI 支持的语言列表
AI_SUPPORT_LANGUAGES = [
    LanguageType.EN_US,
    LanguageType.ZH_CN,
    LanguageType.ZH_TW,
    LanguageType.KO_KR,
]

# 所有目标语言（排除源语言英语）
TARGET_LANGUAGES = [lang for lang in LanguageType if lang != LanguageType.EN_US]


def language_to_chinese(lang: LanguageType) -> str:
    """将语言代码转换为中文名称"""
    mapping = {
        LanguageType.DE_DE: "德语",
        LanguageType.EN_US: "英语",
        LanguageType.ES_ES: "西班牙语",
        LanguageType.FR_FR: "法语",
        LanguageType.JA_JP: "日语",
        LanguageType.PT_BR: "葡萄牙语",
        LanguageType.RU_RU: "俄语",
        LanguageType.UK_UA: "乌克兰语",
        LanguageType.VI_VN: "越南语",
        LanguageType.ZH_CN: "简体中文",
        LanguageType.ZH_TW: "繁体中文",
        LanguageType.AR_AE: "阿拉伯语",
        LanguageType.NL_NL: "荷兰语",
        LanguageType.TR_TR: "土耳其语",
        LanguageType.KO_KR: "韩语",
    }
    return mapping.get(lang, "英语")


def language_to_english(lang: LanguageType) -> str:
    """将语言代码转换为英文名称"""
    mapping = {
        LanguageType.DE_DE: "German",
        LanguageType.EN_US: "English",
        LanguageType.ES_ES: "Spanish",
        LanguageType.FR_FR: "French",
        LanguageType.JA_JP: "Japanese",
        LanguageType.PT_BR: "Portuguese",
        LanguageType.RU_RU: "Russian",
        LanguageType.UK_UA: "Ukrainian",
        LanguageType.VI_VN: "Vietnamese",
        LanguageType.ZH_CN: "Simplified Chinese",
        LanguageType.ZH_TW: "Traditional Chinese",
        LanguageType.AR_AE: "Arabic",
        LanguageType.NL_NL: "Dutch",
        LanguageType.TR_TR: "Turkish",
        LanguageType.KO_KR: "Korean",
    }
    return mapping.get(lang, "English")


class ModelType(str, Enum):
    """测试模型类型"""

    GPT_MINI = "gpt-5-mini"
    GPT = "gpt-5.2"
    CLAUDE_SONNET = "claude-sonnet-4-5-20250929"
    CLAUDE_OPUS = "claude-opus-4-6"
    GEMINI_FLASH = "gemini-3-flash-preview"
    GEMINI_PRO = "gemini-3-pro-preview"


@dataclass
class GlossaryEntry:
    """术语表条目"""

    term_id: str
    definition: str
    part_of_speech: str
    term_en: str
    do_not_translate: bool = False
    translations: dict[str, str] = field(default_factory=dict)


@dataclass
class TranslationResult:
    """翻译结果"""

    source_text: str
    source_key: str
    target_lang: LanguageType
    translated_text: str
    model: ModelType
    latency_ms: float
    glossary_terms_found: list[str] = field(default_factory=list)
    glossary_terms_matched: list[str] = field(default_factory=list)


@dataclass
class EvaluationMetrics:
    """评估指标"""

    model: ModelType
    target_lang: LanguageType
    total_translations: int = 0
    avg_latency_ms: float = 0.0
    glossary_match_rate: float = 0.0
    translation_completeness: float = 0.0  # 翻译完整性（非空率）
    error_count: int = 0


class GlossaryLoader:
    """术语表加载器（支持 JSON 格式）"""

    def __init__(self, glossary_path: Path):
        self.glossary_path = glossary_path
        self.entries: list[GlossaryEntry] = []
        self.term_lookup: dict[str, GlossaryEntry] = {}  # 英文术语 -> 条目

    def load(self, max_entries: int | None = None) -> list[GlossaryEntry]:
        """加载术语表（从 JSON 文件）"""
        if not self.glossary_path.exists():
            raise FileNotFoundError(f"Glossary file not found: {self.glossary_path}")

        with open(self.glossary_path, encoding="utf-8") as f:
            data: dict[str, dict[str, str]] = json.load(f)

        count = 0
        for term_en, translations in data.items():
            if max_entries and count >= max_entries:
                break

            # 检查是否所有翻译都与英文术语相同（即 Do Not Translate）
            unique_values = set(translations.values())
            do_not_translate = len(unique_values) == 1 and term_en in unique_values

            entry = GlossaryEntry(
                term_id="",
                definition="",
                part_of_speech="",
                term_en=term_en,
                do_not_translate=do_not_translate,
                translations=translations,
            )
            self.entries.append(entry)
            # 建立查找索引（忽略大小写）
            self.term_lookup[entry.term_en.lower()] = entry
            count += 1

        return self.entries

    def find_terms_in_text(self, text: str) -> list[GlossaryEntry]:
        """在文本中查找术语表中的术语"""
        found = []
        text_lower = text.lower()
        for term, entry in self.term_lookup.items():
            if term in text_lower:
                found.append(entry)
        return found

    def get_expected_translation(
        self, term_en: str, target_lang: LanguageType
    ) -> str | None:
        """获取术语的预期翻译"""
        entry = self.term_lookup.get(term_en.lower())
        if entry:
            # 如果是不翻译术语，返回原文
            if entry.do_not_translate:
                return entry.term_en
            # 返回目标语言翻译
            return entry.translations.get(target_lang.value)
        return None


class SourceTextLoader:
    """源文本加载器"""

    def __init__(self, source_path: Path):
        self.source_path = source_path
        self.texts: dict[str, str] = {}  # key -> text

    def load(self, max_entries: int | None = None) -> dict[str, str]:
        """加载源文本，展平嵌套 JSON"""
        if not self.source_path.exists():
            raise FileNotFoundError(f"Source file not found: {self.source_path}")

        with open(self.source_path, encoding="utf-8") as f:
            data = json.load(f)

        self._flatten_json(data, "")

        # 限制条目数量
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


class TranslationClient:
    """翻译客户端（支持多种模型）"""

    def __init__(self, glossary_loader: GlossaryLoader):
        self.glossary_loader = glossary_loader
        self._openai_client = None
        self._anthropic_client = None
        self._genai_client = None

    @property
    def openai_client(self):
        """延迟初始化 OpenAI 客户端"""
        if self._openai_client is None:
            from openai import AsyncOpenAI

            self._openai_client = AsyncOpenAI()
        return self._openai_client

    @property
    def anthropic_client(self):
        """延迟初始化 Anthropic 客户端"""
        if self._anthropic_client is None:
            from anthropic import AsyncAnthropic

            self._anthropic_client = AsyncAnthropic()
        return self._anthropic_client

    @property
    def genai_client(self):
        """延迟初始化 Google GenAI 客户端"""
        if self._genai_client is None:
            from google import genai

            # 禁用自动关闭以避免 aclose() 时的 AttributeError
            self._genai_client = genai.Client()
        return self._genai_client

    async def close(self) -> None:
        """关闭所有客户端连接"""
        if self._openai_client is not None:
            await self._openai_client.close()
            self._openai_client = None

        if self._anthropic_client is not None:
            await self._anthropic_client.close()
            self._anthropic_client = None

        # Google GenAI 客户端不需要显式关闭，设为 None 让 GC 处理
        self._genai_client = None

    def _build_translation_prompt(
        self,
        text: str,
        target_lang: LanguageType,
        glossary_terms: list[GlossaryEntry],
    ) -> str:
        """构建翻译提示词"""
        target_lang_name = language_to_english(target_lang)

        # 构建术语表部分
        glossary_section = ""
        if glossary_terms:
            glossary_lines = []
            for entry in glossary_terms:
                if entry.do_not_translate:
                    glossary_lines.append(
                        f"- '{entry.term_en}' -> Keep as '{entry.term_en}' (Do Not Translate)"
                    )
                else:
                    expected = entry.translations.get(target_lang.value)
                    if expected:
                        glossary_lines.append(
                            f"- '{entry.term_en}' -> '{expected}'"
                        )
            if glossary_lines:
                glossary_section = (
                    "\n\nGlossary (use these exact translations):\n"
                    + "\n".join(glossary_lines)
                )

        prompt = f"""Translate the following text from English to {target_lang_name}.

Rules:
1. Preserve all placeholders like {{n}}, {{name}}, etc.
2. Keep brand names and technical terms consistent with the glossary
3. Maintain the same tone and style as the original
4. Return ONLY the translated text, no explanations{glossary_section}

Text to translate:
{text}"""

        return prompt

    async def translate_with_openai(
        self,
        text: str,
        source_key: str,
        target_lang: LanguageType,
        model: str = "gpt-5-mini",
    ) -> TranslationResult:
        """使用 OpenAI 模型翻译"""
        glossary_terms = self.glossary_loader.find_terms_in_text(text)
        prompt = self._build_translation_prompt(text, target_lang, glossary_terms)

        start_time = time.perf_counter()
        try:
            response = await self.openai_client.chat.completions.create(
                model=model,
                messages=[
                    {"role": "system", "content": "You are a professional translator."},
                    {"role": "user", "content": prompt},
                ]
            )
            translated_text = response.choices[0].message.content.strip()
        except Exception as e:
            translated_text = f"[ERROR: {e}]"

        latency_ms = (time.perf_counter() - start_time) * 1000

        return TranslationResult(
            source_text=text,
            source_key=source_key,
            target_lang=target_lang,
            translated_text=translated_text,
            model=ModelType.GPT_MINI,
            latency_ms=latency_ms,
            glossary_terms_found=[e.term_en for e in glossary_terms],
        )

    async def translate_with_anthropic(
        self,
        text: str,
        source_key: str,
        target_lang: LanguageType,
        model: str = "claude-sonnet-4-5-20250929",
    ) -> TranslationResult:
        """使用 Anthropic Claude 模型翻译"""
        glossary_terms = self.glossary_loader.find_terms_in_text(text)
        prompt = self._build_translation_prompt(text, target_lang, glossary_terms)

        start_time = time.perf_counter()
        try:
            response = await self.anthropic_client.messages.create(
                model=model,
                messages=[{"role": "user", "content": prompt}],
            )
            translated_text = response.content[0].text.strip()
        except Exception as e:
            translated_text = f"[ERROR: {e}]"

        latency_ms = (time.perf_counter() - start_time) * 1000

        return TranslationResult(
            source_text=text,
            source_key=source_key,
            target_lang=target_lang,
            translated_text=translated_text,
            model=ModelType.CLAUDE_SONNET,
            latency_ms=latency_ms,
            glossary_terms_found=[e.term_en for e in glossary_terms],
        )

    async def translate_with_gemini(
        self,
        text: str,
        source_key: str,
        target_lang: LanguageType,
        model: str = "gemini-3-flash-preview",
    ) -> TranslationResult:
        """使用 Google Gemini 模型翻译"""
        glossary_terms = self.glossary_loader.find_terms_in_text(text)
        prompt = self._build_translation_prompt(text, target_lang, glossary_terms)

        start_time = time.perf_counter()
        try:
            response = await self.genai_client.aio.models.generate_content(
                model=model,
                contents=prompt,
            )
            translated_text = response.text.strip()
        except Exception as e:
            translated_text = f"[ERROR: {e}]"

        latency_ms = (time.perf_counter() - start_time) * 1000

        return TranslationResult(
            source_text=text,
            source_key=source_key,
            target_lang=target_lang,
            translated_text=translated_text,
            model=ModelType.GEMINI_FLASH,
            latency_ms=latency_ms,
            glossary_terms_found=[e.term_en for e in glossary_terms],
        )


class TranslationEvaluator:
    """翻译质量评估器"""

    def __init__(self, glossary_loader: GlossaryLoader):
        self.glossary_loader = glossary_loader

    def evaluate_glossary_match(
        self,
        result: TranslationResult,
    ) -> float:
        """评估术语匹配率"""
        if not result.glossary_terms_found:
            return 1.0  # 没有术语需要匹配

        matched = 0
        for term_en in result.glossary_terms_found:
            expected = self.glossary_loader.get_expected_translation(
                term_en, result.target_lang
            )
            if expected and expected.lower() in result.translated_text.lower():
                matched += 1
                result.glossary_terms_matched.append(term_en)

        return matched / len(result.glossary_terms_found)

    def calculate_metrics(
        self,
        results: list[TranslationResult],
        model: ModelType,
        target_lang: LanguageType,
    ) -> EvaluationMetrics:
        """计算评估指标"""
        filtered = [
            r for r in results if r.model == model and r.target_lang == target_lang
        ]

        if not filtered:
            return EvaluationMetrics(model=model, target_lang=target_lang)

        # 计算平均延迟
        latencies = [r.latency_ms for r in filtered]
        avg_latency = sum(latencies) / len(latencies)

        # 计算术语匹配率
        match_rates = [self.evaluate_glossary_match(r) for r in filtered]
        avg_match_rate = sum(match_rates) / len(match_rates)

        # 计算翻译完整性
        non_empty = sum(
            1 for r in filtered if r.translated_text and not r.translated_text.startswith("[ERROR")
        )
        completeness = non_empty / len(filtered)

        # 错误计数
        errors = sum(1 for r in filtered if r.translated_text.startswith("[ERROR"))

        return EvaluationMetrics(
            model=model,
            target_lang=target_lang,
            total_translations=len(filtered),
            avg_latency_ms=avg_latency,
            glossary_match_rate=avg_match_rate,
            translation_completeness=completeness,
            error_count=errors,
        )


class AblationExperiment:
    """消融实验主类"""

    def __init__(
        self,
        glossary_path: Path = GLOSSARY_PATH,
        source_path: Path = SOURCE_PATH,
        output_dir: Path = OUTPUT_DIR,
        max_glossary_entries: int = 500,
        max_source_entries: int = 50,
        target_languages: list[LanguageType] | None = None,
        batch_size: int = 5,
    ):
        self.glossary_loader = GlossaryLoader(glossary_path)
        self.source_loader = SourceTextLoader(source_path)
        self.output_dir = output_dir
        self.max_glossary_entries = max_glossary_entries
        self.max_source_entries = max_source_entries
        self.target_languages = target_languages or AI_SUPPORT_LANGUAGES[1:]  # 排除 EN_US
        self.batch_size = batch_size

        self.translation_client: TranslationClient | None = None
        self.evaluator: TranslationEvaluator | None = None
        self.results: list[TranslationResult] = []

    def setup(self) -> None:
        """初始化实验"""
        # 加载术语表
        self.glossary_loader.load(max_entries=self.max_glossary_entries)
        print(f"[setup] 加载术语表完成，共 {len(self.glossary_loader.entries)} 条")

        # 加载源文本
        self.source_loader.load(max_entries=self.max_source_entries)
        print(f"[setup] 加载源文本完成，共 {len(self.source_loader.texts)} 条")

        # 初始化翻译客户端
        self.translation_client = TranslationClient(self.glossary_loader)
        self.evaluator = TranslationEvaluator(self.glossary_loader)

        # 创建输出目录
        self.output_dir.mkdir(parents=True, exist_ok=True)
        print(f"[setup] 批量大小: {self.batch_size}")

    async def run_translation_batch(
        self,
        model: ModelType,
        target_lang: LanguageType,
    ) -> list[TranslationResult]:
        """运行单个模型的翻译批次（支持并发）"""
        results = []
        translate_func = {
            ModelType.GPT_MINI: self.translation_client.translate_with_openai,
            ModelType.GPT: self.translation_client.translate_with_openai,
            ModelType.CLAUDE_SONNET: self.translation_client.translate_with_anthropic,
            ModelType.CLAUDE_OPUS: self.translation_client.translate_with_anthropic,
            ModelType.GEMINI_FLASH: self.translation_client.translate_with_gemini,
            ModelType.GEMINI_PRO: self.translation_client.translate_with_gemini,
        }[model]

        # 将源文本转换为列表
        items = list(self.source_loader.texts.items())

        # 按 batch_size 分批处理
        for i in range(0, len(items), self.batch_size):
            batch = items[i : i + self.batch_size]

            # 并发执行当前批次的翻译
            tasks = [
                translate_func(text, key, target_lang) for key, text in batch
            ]
            batch_results = await asyncio.gather(*tasks, return_exceptions=True)

            # 处理结果
            for idx, result in enumerate(batch_results):
                if isinstance(result, Exception):
                    # 创建错误结果
                    key, text = batch[idx]
                    results.append(
                        TranslationResult(
                            source_text=text,
                            source_key=key,
                            target_lang=target_lang,
                            translated_text=f"[ERROR: {result}]",
                            model=model,
                            latency_ms=0,
                        )
                    )
                else:
                    results.append(result)

            # 批次间速率限制
            if i + self.batch_size < len(items):
                await asyncio.sleep(0.5)

        return results

    async def run_experiment(self) -> dict[str, Any]:
        """运行完整实验"""
        self.setup()

        all_metrics: list[EvaluationMetrics] = []

        try:
            for model in ModelType:
                print(f"\n[experiment] 开始测试模型: {model.value}")
                for target_lang in self.target_languages:
                    print(f"  [experiment] 目标语言: {language_to_chinese(target_lang)}")

                    batch_results = await self.run_translation_batch(model, target_lang)
                    self.results.extend(batch_results)

                    metrics = self.evaluator.calculate_metrics(
                        batch_results, model, target_lang
                    )
                    all_metrics.append(metrics)

                    print(
                        f"    完成: {metrics.total_translations} 条, "
                        f"平均延迟: {metrics.avg_latency_ms:.2f}ms, "
                        f"术语匹配率: {metrics.glossary_match_rate:.2%}, "
                        f"错误数: {metrics.error_count}"
                    )

            # 生成报告
            report = self._generate_report(all_metrics)
            self._save_results(report)

            return report
        finally:
            # 确保关闭所有客户端连接
            if self.translation_client:
                await self.translation_client.close()

    def _generate_report(
        self, metrics: list[EvaluationMetrics]
    ) -> dict[str, Any]:
        """生成实验报告"""
        report = {
            "experiment_info": {
                "models": [m.value for m in ModelType],
                "target_languages": [l.value for l in self.target_languages],
                "source_entries": len(self.source_loader.texts),
                "glossary_entries": len(self.glossary_loader.entries),
            },
            "metrics_by_model": {},
            "metrics_by_language": {},
            "summary": {},
        }

        # 按模型汇总
        for model in ModelType:
            model_metrics = [m for m in metrics if m.model == model]
            if model_metrics:
                report["metrics_by_model"][model.value] = {
                    "avg_latency_ms": sum(m.avg_latency_ms for m in model_metrics)
                    / len(model_metrics),
                    "avg_glossary_match_rate": sum(
                        m.glossary_match_rate for m in model_metrics
                    )
                    / len(model_metrics),
                    "avg_completeness": sum(
                        m.translation_completeness for m in model_metrics
                    )
                    / len(model_metrics),
                    "total_errors": sum(m.error_count for m in model_metrics),
                }

        # 按语言汇总
        for lang in self.target_languages:
            lang_metrics = [m for m in metrics if m.target_lang == lang]
            if lang_metrics:
                report["metrics_by_language"][lang.value] = {
                    "avg_latency_ms": sum(m.avg_latency_ms for m in lang_metrics)
                    / len(lang_metrics),
                    "avg_glossary_match_rate": sum(
                        m.glossary_match_rate for m in lang_metrics
                    )
                    / len(lang_metrics),
                }

        # 总体汇总
        if metrics:
            report["summary"] = {
                "total_translations": sum(m.total_translations for m in metrics),
                "overall_avg_latency_ms": sum(m.avg_latency_ms for m in metrics)
                / len(metrics),
                "overall_glossary_match_rate": sum(
                    m.glossary_match_rate for m in metrics
                )
                / len(metrics),
                "total_errors": sum(m.error_count for m in metrics),
            }

        return report

    def _save_results(self, report: dict[str, Any]) -> None:
        """保存结果"""
        import datetime

        timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")

        # 保存报告
        report_path = self.output_dir / f"report_{timestamp}.json"
        with open(report_path, "w", encoding="utf-8") as f:
            json.dump(report, f, ensure_ascii=False, indent=2)
        print(f"\n[save] 报告已保存: {report_path}")

        # 保存详细结果 (JSON)
        results_path = self.output_dir / f"results_{timestamp}.json"
        results_data = [
            {
                "source_key": r.source_key,
                "source_text": r.source_text,
                "target_lang": r.target_lang.value,
                "translated_text": r.translated_text,
                "model": r.model.value,
                "latency_ms": r.latency_ms,
                "glossary_terms_found": r.glossary_terms_found,
                "glossary_terms_matched": r.glossary_terms_matched,
            }
            for r in self.results
        ]
        with open(results_path, "w", encoding="utf-8") as f:
            json.dump(results_data, f, ensure_ascii=False, indent=2)
        print(f"[save] 详细结果已保存: {results_path}")

        # 保存模型比较 CSV
        self._save_comparison_csv(timestamp)

    def _save_comparison_csv(self, timestamp: str) -> None:
        """保存模型比较 CSV，方便横向对比不同模型的翻译结果"""
        # 按 (source_key, target_lang) 分组结果
        grouped: dict[tuple[str, str], dict[str, TranslationResult]] = {}
        for r in self.results:
            key = (r.source_key, r.target_lang.value)
            if key not in grouped:
                grouped[key] = {}
            grouped[key][r.model.value] = r

        # 获取所有模型名称
        models = [m.value for m in ModelType]

        # 构建 CSV 表头
        headers = [
            "source_key",
            "target_lang",
            "target_lang_name",
            "source_text",
        ]
        for model in models:
            headers.append(f"{model}_translation")

        # 构建 CSV 行
        rows = []
        for (source_key, target_lang), model_results in sorted(grouped.items()):
            # 获取源文本（从任意一个结果中获取）
            source_text = ""
            for r in model_results.values():
                source_text = r.source_text
                break

            row = {
                "source_key": source_key,
                "target_lang": target_lang,
                "target_lang_name": language_to_chinese(LanguageType(target_lang)),
                "source_text": source_text,
            }

            for model in models:
                result = model_results.get(model)
                row[f"{model}_translation"] = result.translated_text if result else ""

            rows.append(row)

        # 写入 CSV
        csv_path = self.output_dir / f"comparison_{timestamp}.csv"
        with open(csv_path, "w", encoding="utf-8-sig", newline="") as f:
            writer = csv.DictWriter(f, fieldnames=headers)
            writer.writeheader()
            writer.writerows(rows)
        print(f"[save] 模型比较 CSV 已保存: {csv_path}")


# ============== Pytest 测试用例 ==============


class TestGlossaryLoader:
    """术语表加载器测试"""

    def test_load_glossary(self):
        """测试加载术语表"""
        if not GLOSSARY_PATH.exists():
            pytest.skip("Glossary file not found")

        loader = GlossaryLoader(GLOSSARY_PATH)
        entries = loader.load(max_entries=100)

        assert len(entries) > 0
        assert all(e.term_en for e in entries)

    def test_find_terms_in_text(self):
        """测试在文本中查找术语"""
        if not GLOSSARY_PATH.exists():
            pytest.skip("Glossary file not found")

        loader = GlossaryLoader(GLOSSARY_PATH)
        loader.load(max_entries=100)

        # 测试查找
        text = "Please check your Example account for the latest NFT staking rewards."
        found = loader.find_terms_in_text(text)

        # 应该能找到 Example, NFT, staking 等术语
        found_terms = [e.term_en.lower() for e in found]
        assert any(term in ["example", "nft", "staking"] for term in found_terms)


class TestSourceTextLoader:
    """源文本加载器测试"""

    def test_load_source(self):
        """测试加载源文本"""
        if not SOURCE_PATH.exists():
            pytest.skip("Source file not found")

        loader = SourceTextLoader(SOURCE_PATH)
        texts = loader.load(max_entries=50)

        assert len(texts) > 0
        assert all(isinstance(v, str) for v in texts.values())


class TestTranslationClient:
    """翻译客户端测试"""

    @pytest.fixture
    def client(self):
        """创建翻译客户端"""
        if not GLOSSARY_PATH.exists():
            pytest.skip("Glossary file not found")

        glossary_loader = GlossaryLoader(GLOSSARY_PATH)
        glossary_loader.load(max_entries=100)
        return TranslationClient(glossary_loader)

    @pytest.mark.asyncio
    async def test_translate_with_openai(self, client):
        """测试 OpenAI 翻译"""
        if not os.getenv("OPENAI_API_KEY"):
            pytest.skip("OPENAI_API_KEY not set")

        result = await client.translate_with_openai(
            text="Loading...",
            source_key="test.loading",
            target_lang=LanguageType.ZH_CN,
        )

        assert result.translated_text
        assert result.model == ModelType.GPT
        assert result.latency_ms > 0

    @pytest.mark.asyncio
    async def test_translate_with_anthropic(self, client):
        """测试 Anthropic 翻译"""
        if not os.getenv("ANTHROPIC_API_KEY"):
            pytest.skip("ANTHROPIC_API_KEY not set")

        result = await client.translate_with_anthropic(
            text="Loading...",
            source_key="test.loading",
            target_lang=LanguageType.ZH_CN,
        )

        assert result.translated_text
        assert result.model == ModelType.CLAUDE
        assert result.latency_ms > 0

    @pytest.mark.asyncio
    async def test_translate_with_gemini(self, client):
        """测试 Gemini 翻译"""
        # Gemini 使用 VertexAI 配置
        result = await client.translate_with_gemini(
            text="Loading...",
            source_key="test.loading",
            target_lang=LanguageType.ZH_CN,
        )

        assert result.translated_text
        assert result.model == ModelType.GEMINI
        assert result.latency_ms > 0


class TestAblationExperiment:
    """消融实验测试"""

    @pytest.mark.asyncio
    async def test_run_mini_experiment(self):
        """运行小规模实验测试"""
        # 检查必要文件和环境变量
        if not GLOSSARY_PATH.exists() or not SOURCE_PATH.exists():
            pytest.skip("Data files not found")

        has_keys = (
            os.getenv("OPENAI_API_KEY")
            or os.getenv("ANTHROPIC_API_KEY")
            or os.getenv("GOOGLE_CLOUD_PROJECT")
        )
        if not has_keys:
            pytest.skip("No API keys configured")

        experiment = AblationExperiment(
            max_glossary_entries=50,
            max_source_entries=5,
            target_languages=[LanguageType.ZH_CN],  # 只测试中文
        )

        report = await experiment.run_experiment()

        assert "experiment_info" in report
        assert "summary" in report
        assert report["summary"]["total_translations"] > 0


# ============== 命令行入口 ==============


def _ignore_genai_aclose_error(loop: asyncio.AbstractEventLoop, context: dict[str, Any]) -> None:
    """忽略 google-genai 库的 aclose 错误（已知问题）"""
    exception = context.get("exception")
    if exception and isinstance(exception, AttributeError):
        if "_async_httpx_client" in str(exception):
            # 忽略 google-genai 的清理错误
            return
    # 其他异常使用默认处理
    loop.default_exception_handler(context)


async def main():
    """命令行入口"""
    import argparse

    # 设置异常处理器以忽略 google-genai 的 aclose 错误
    loop = asyncio.get_running_loop()
    loop.set_exception_handler(_ignore_genai_aclose_error)

    parser = argparse.ArgumentParser(description="翻译模型消融实验")
    parser.add_argument(
        "--max-glossary",
        type=int,
        default=500,
        help="最大术语表条目数",
    )
    parser.add_argument(
        "--max-source",
        type=int,
        default=5,
        help="最大源文本条目数",
    )
    parser.add_argument(
        "--languages",
        nargs="+",
        default=["zh-CN", "zh-TW", "ko-KR"],
        help="目标语言列表",
    )
    parser.add_argument(
        "--batch-size",
        type=int,
        default=5,
        help="批量翻译大小（并发数）",
    )

    args = parser.parse_args()

    # 解析语言
    target_langs = []
    for lang_str in args.languages:
        try:
            target_langs.append(LanguageType(lang_str))
        except ValueError:
            print(f"警告: 不支持的语言 {lang_str}")

    if not target_langs:
        target_langs = [LanguageType.ZH_CN, LanguageType.ZH_TW, LanguageType.KO_KR]

    experiment = AblationExperiment(
        max_glossary_entries=args.max_glossary,
        max_source_entries=args.max_source,
        target_languages=target_langs,
        batch_size=args.batch_size,
    )

    report = await experiment.run_experiment()

    # 打印汇总
    print("\n" + "=" * 60)
    print("实验汇总")
    print("=" * 60)

    for model, metrics in report["metrics_by_model"].items():
        print(f"\n{model}:")
        print(f"  平均延迟: {metrics['avg_latency_ms']:.2f}ms")
        print(f"  术语匹配率: {metrics['avg_glossary_match_rate']:.2%}")
        print(f"  翻译完整率: {metrics['avg_completeness']:.2%}")
        print(f"  错误数: {metrics['total_errors']}")


if __name__ == "__main__":
    asyncio.run(main())
