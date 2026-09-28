"""
一致性评审 Agent

检查多语言翻译的术语一致性
"""

import json
import re
from typing import Any

from app.agents.base import BaseAgent
from app.core.constants import get_language_name
from app.logger import logger
from app.schemas.glossary import Glossary
from app.schemas.review import (
    ConsistencyReviewResult,
    TermConsistencyIssue,
)
from app.schemas.translation import TranslationItem


class ConsistencyReviewAgent(BaseAgent):
    """
    一致性评审 Agent

    检查多语言翻译中术语使用的一致性
    """

    agent_type = "consistency_review"

    def __init__(
        self,
        glossary: Glossary | None = None,
        **kwargs: Any,
    ):
        """
        初始化一致性评审 Agent

        Args:
            glossary: 术语表
            **kwargs: 传递给基类的参数
        """
        super().__init__(**kwargs)
        self.glossary = glossary or Glossary()

    def _build_prompt(
        self,
        source_text: str,
        translations: list[TranslationItem],
        glossary_terms: list[str],
        source_text_2: str | None = None,
    ) -> str:
        """构建一致性评审提示词"""
        # 构建翻译列表
        translations_text = ""
        for item in translations:
            lang_name = get_language_name(item.target_lang)
            translations_text += (
                f"\n{lang_name} ({item.target_lang}):\n" f"{item.translated_text}\n"
            )

        # 构建术语表部分（区分人工术语库和 Binance 术语）
        glossary_section = ""
        if glossary_terms:
            curated_terms: list[str] = []
            binance_terms_list: list[str] = []

            for term_en in glossary_terms:
                entry = self.glossary.term_lookup.get(term_en.lower())
                if entry and entry.source == "binance.com":
                    binance_terms_list.append(term_en)
                else:
                    curated_terms.append(term_en)

            # 人工维护术语（最高优先级）
            if curated_terms:
                glossary_section += (
                    "\n\nOfficial Glossary "
                    "(HIGHEST PRIORITY — must match exactly):\n"
                )
                for term_en in curated_terms:
                    glossary_section += f"\nTerm: '{term_en}'\n"
                    for item in translations:
                        expected = self.glossary.get_expected_translation(
                            term_en, item.target_lang
                        )
                        if expected:
                            lang_name = get_language_name(item.target_lang)
                            glossary_section += f"  {lang_name}: '{expected}'\n"

            # Binance 术语（次要参考）
            if binance_terms_list:
                glossary_section += (
                    "\n\nBinance Exchange Reference "
                    "(secondary reference, deviations are minor):\n"
                )
                for term_en in binance_terms_list:
                    glossary_section += f"\nTerm: '{term_en}'\n"
                    for item in translations:
                        expected = self.glossary.get_expected_translation(
                            term_en, item.target_lang
                        )
                        if expected:
                            lang_name = get_language_name(item.target_lang)
                            glossary_section += f"  {lang_name}: '{expected}'\n"

        # 构建术语匹配信号（来自翻译阶段）
        matching_signals = "\n\nTerm Matching Signals from translation stage:"
        for item in translations:
            lang_name = get_language_name(item.target_lang)
            found_terms = ", ".join(item.glossary_terms_found[:20]) or "none"
            matched_terms = ", ".join(item.glossary_terms_matched[:20]) or "none"
            matching_signals += (
                f"\n- {lang_name} ({item.target_lang}) found: {found_terms}"
                f"\n  matched: {matched_terms}"
            )

        if source_text and source_text_2:
            source_section = (
                f"Source text (English):\n{source_text}\n\n"
                f"Source text (Simplified Chinese):\n{source_text_2}"
            )
        elif source_text:
            source_section = f"Source text (English):\n{source_text}"
        else:
            source_section = f"Source text (Simplified Chinese):\n{source_text_2}"

        return f"""You are a translation consistency reviewer \
specializing in cryptocurrency and financial trading content.
Check if the following translations use terminology consistently across all languages.

{source_section}

Translations:{translations_text}
{glossary_section}
{matching_signals}

### Priority Rules
1. **Official Glossary terms (HIGHEST PRIORITY):** Translations MUST match the official \
glossary exactly. Any deviation from official glossary is a FAIL.
2. **Binance Exchange Reference (secondary):** Prefer Binance standard terms, but \
deviations are minor issues — do NOT fail solely for Binance term differences.
3. **English Priority Rule:** When English and Chinese source texts conflict in meaning, \
English is the authoritative source. If translations follow the English meaning, \
do NOT fail for deviating from the Chinese text. Minor Binance reference differences \
should NOT cause a FAIL.

### Check Items
1. Do translations match the official glossary terms exactly? (MANDATORY)
2. Are coin/token symbols (BTC, ETH, USDT) and protocol names preserved without translation?
3. Are cryptocurrency and trading terms translated consistently across languages?
4. Do translations reasonably align with Binance exchange reference terms? (minor check)

Provide your response in the following JSON format:
{{
    "passed": <true/false>,
    "feedback": "<中文反馈，通过时留空；未通过时50-100字详细说明问题及建议>",
    "issues": [
        {{
            "term_en": "<English term>",
            "expected_translations": {{"<lang_code>": "<expected>", ...}},
            "actual_translations": {{"<lang_code>": "<actual>", ...}},
            "issue_description": "<中文描述，30-60字，说明不一致的具体内容和建议修正>"
        }}
    ],
    "checked_terms_count": <number>,
    "inconsistent_terms_count": <number>
}}

Important rules for feedback and issue_description:
- feedback 和 issue_description 必须使用中文
- 通过时 feedback 为空字符串""
- 未通过时 feedback 需详细说明：哪些术语不一致、当前各语言分别翻译为什么、应该翻译为什么
- issue_description 需具体说明：该术语在哪些语言中翻译不一致、期望译文是什么、当前译文是什么
- Only report issues for official glossary term deviations as FAIL
- Binance reference deviations should be noted but NOT cause passed=false alone

Return ONLY the JSON object, no additional text."""

    def _parse_response(self, response: str) -> dict[str, Any]:
        """解析 LLM 响应"""
        # 尝试提取 JSON
        json_match = re.search(r"\{[\s\S]*\}", response)
        if not json_match:
            logger.warning(
                f"[ConsistencyReviewAgent._parse_response] "
                f"无法提取 JSON: {response[:200]}"
            )
            return {
                "passed": True,
                "feedback": "解析一致性响应失败",
                "issues": [],
                "checked_terms_count": 0,
                "inconsistent_terms_count": 0,
            }

        try:
            return json.loads(json_match.group())
        except json.JSONDecodeError as e:
            logger.warning(
                f"[ConsistencyReviewAgent._parse_response] JSON 解析失败: {e}"
            )
            return {
                "passed": True,
                "feedback": "解析一致性响应失败",
                "issues": [],
                "checked_terms_count": 0,
                "inconsistent_terms_count": 0,
            }

    async def run(
        self,
        source_text: str,
        translations: list[TranslationItem],
        source_text_2: str | None = None,
    ) -> ConsistencyReviewResult:
        """
        执行一致性评审

        Args:
            source_text: 源文本
            translations: 各语言翻译结果列表

        Returns:
            ConsistencyReviewResult 包含评审结果
        """
        logger.info(
            f"[ConsistencyReviewAgent.run] 开始一致性评审, "
            f"translations_count={len(translations)}"
        )

        # 如果只有一种语言，直接通过
        if len(translations) <= 1:
            return ConsistencyReviewResult(
                passed=True,
                feedback="仅一种语言，跳过",
                issues=[],
                checked_terms_count=0,
                inconsistent_terms_count=0,
            )

        # 收集所有找到的术语
        all_terms: set[str] = set()
        for item in translations:
            all_terms.update(item.glossary_terms_found)

        if not all_terms:
            return ConsistencyReviewResult(
                passed=True,
                feedback="未发现术语，跳过",
                issues=[],
                checked_terms_count=0,
                inconsistent_terms_count=0,
            )

        # 构建提示词
        prompt = self._build_prompt(
            source_text, translations, list(all_terms), source_text_2
        )

        # 调用 LLM
        try:
            response = await self._call_llm(
                messages=[
                    {
                        "role": "system",
                        "content": (
                            "You are a translation consistency reviewer "
                            "specializing in cryptocurrency, blockchain, and "
                            "financial trading content. Official glossary terms "
                            "must match exactly (highest priority). Binance "
                            "exchange terms are secondary reference only. "
                            "When English and Chinese sources conflict, English is authoritative. "
                            "Minor Binance term differences should not cause failure. "
                            "Always respond with valid JSON."
                        ),
                    },
                    {"role": "user", "content": prompt},
                ],
                temperature=0.2,
            )
        except Exception as e:
            logger.error(f"[ConsistencyReviewAgent.run] 评审失败: {e}")
            # 返回默认通过结果
            return ConsistencyReviewResult(
                passed=True,
                feedback=f"一致性评审失败: {e}",
                issues=[],
                checked_terms_count=len(all_terms),
                inconsistent_terms_count=0,
            )

        # 解析响应
        parsed = self._parse_response(response)

        # 构建问题列表
        issues = []
        for issue_data in parsed.get("issues", []):
            # 过滤掉 None 值，确保字典值都是字符串
            expected = issue_data.get("expected_translations", {}) or {}
            actual = issue_data.get("actual_translations", {}) or {}
            expected_clean = {k: v for k, v in expected.items() if v is not None}
            actual_clean = {k: v for k, v in actual.items() if v is not None}

            issues.append(
                TermConsistencyIssue(
                    term_en=issue_data.get("term_en", "") or "",
                    expected_translations=expected_clean,
                    actual_translations=actual_clean,
                    issue_description=issue_data.get("issue_description", "") or "",
                )
            )

        result = ConsistencyReviewResult(
            passed=parsed.get("passed", True),
            feedback=parsed.get("feedback", ""),
            issues=issues,
            checked_terms_count=parsed.get("checked_terms_count", len(all_terms)),
            inconsistent_terms_count=parsed.get(
                "inconsistent_terms_count", len(issues)
            ),
        )

        logger.info(
            f"[ConsistencyReviewAgent.run] 一致性评审完成, "
            f"passed={result.passed}, issues={len(issues)}"
        )

        return result
