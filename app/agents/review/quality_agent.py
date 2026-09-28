"""
质量评审 Agent

评估翻译质量并给出评分和反馈
"""

import json
import re
from typing import Any

from app.agents.base import BaseAgent
from app.core.constants import QUALITY_THRESHOLD, get_language_name
from app.logger import logger
from app.schemas.glossary import GlossaryTerm
from app.schemas.review import QualityReviewResult, QualityScore


class QualityReviewAgent(BaseAgent):
    """
    质量评审 Agent

    评估翻译的准确性、流畅性、术语一致性和风格
    """

    agent_type = "quality_review"
    SYSTEM_PROMPT = (
        "You are a Translation Quality Review Agent for crypto "
        "product UI copy. Evaluate translation quality and output "
        "PASS/FAIL with reasoning. "
        "Priority: Glossary Compliance > Accuracy > "
        "Binance Terminology > Fluency > Style. "
        "Hard Fail (mark=0) ONLY for: official glossary mismatch "
        "(when official glossary exists), untranslated/wrong target language, "
        "core meaning contradiction, or placeholder/number/symbol corruption. "
        "If official glossary is empty, do NOT fail for glossary absence. "
        "Binance terms are secondary reference only and never hard-fail alone. "
        "'no expected translation in review glossary' is a weak hint only, "
        "never use it alone to fail. "
        "When English and Chinese sources conflict, English is the SOLE reference. "
        "A translation that correctly conveys the English meaning is CORRECT, "
        "even if it completely contradicts the Chinese. "
        "Always respond with valid JSON only."
    )

    def __init__(
        self,
        quality_threshold: int = QUALITY_THRESHOLD,
        glossary_terms: list[GlossaryTerm] | None = None,
        curated_glossary_terms: list[GlossaryTerm] | None = None,
        **kwargs: Any,
    ):
        """
        初始化质量评审 Agent

        Args:
            quality_threshold: 质量阈值（0-100）
            glossary_terms: Binance 参考术语列表（次要参考）
            curated_glossary_terms: 人工维护术语列表（最高优先级）
            **kwargs: 传递给基类的参数
        """
        super().__init__(**kwargs)
        self.quality_threshold = quality_threshold
        self.glossary_terms = glossary_terms or []
        self.curated_glossary_terms = curated_glossary_terms or []

    def _build_glossary_reference(self, target_lang: str) -> str:
        """构建术语参考部分，人工术语库优先，Binance 术语次之"""
        sections: list[str] = []

        # 1. 人工维护术语库（最高优先级）
        curated_lines: list[str] = []
        if self.curated_glossary_terms:
            for term in self.curated_glossary_terms[:30]:
                translation = term.get_translation(target_lang)
                if translation:
                    curated_lines.append(f"- '{term.term_en}' -> '{translation}'")
        if curated_lines:
            sections.append(
                "\n\nOfficial Glossary (HIGHEST PRIORITY — "
                "translations MUST match these exactly):\n"
                + "\n".join(curated_lines)
            )
        else:
            sections.append(
                "\n\nOfficial Glossary (HIGHEST PRIORITY): none for this target "
                "language. Do NOT fail for glossary absence."
            )

        # 2. Binance 术语（次要参考）
        binance_lines: list[str] = []
        if self.glossary_terms:
            for term in self.glossary_terms[:20]:
                translation = term.get_translation(target_lang)
                if translation:
                    binance_lines.append(f"- '{term.term_en}' -> '{translation}'")
        if binance_lines:
            sections.append(
                "\n\nBinance Exchange Reference "
                "(secondary reference, deviations are minor issues):\n"
                + "\n".join(binance_lines)
            )
        else:
            sections.append(
                "\n\nBinance Exchange Reference: none for this target language "
                "(do not fail based on Binance absence)."
            )

        return "".join(sections)

    def _build_term_lookup(
        self,
        target_lang: str,
    ) -> dict[str, tuple[str, str, str]]:
        """
        构建术语查找表（小写 term_en -> (展示名称, 预期译文, 来源)）

        来源值:
            - "official": 人工维护术语（最高优先级）
            - "binance": Binance 参考术语（次要参考）
        """
        lookup: dict[str, tuple[str, str, str]] = {}

        # 先放 Binance，后放 Official（确保 Official 覆盖同名术语）
        for term in self.glossary_terms:
            translation = term.get_translation(target_lang)
            if translation:
                lookup[term.term_en.lower()] = (term.term_en, translation, "binance")

        for term in self.curated_glossary_terms:
            translation = term.get_translation(target_lang)
            if translation:
                lookup[term.term_en.lower()] = (term.term_en, translation, "official")

        return lookup

    def _build_term_match_signals(
        self,
        target_lang: str,
        glossary_terms_found: list[str] | None = None,
        glossary_terms_matched: list[str] | None = None,
        glossary_l1_direct_matches: dict[str, str] | None = None,
    ) -> str:
        """
        构建术语匹配信号段，帮助模型进行预期译文 vs 实际译文对比评估。
        """
        found_terms = glossary_terms_found or []
        matched_terms = glossary_terms_matched or []
        l1_matches = glossary_l1_direct_matches or {}
        if not found_terms and not matched_terms and not l1_matches:
            return ""

        # 构建 L1 强制匹配的小写查找集合
        l1_lower_set = {k.lower() for k in l1_matches}

        # 去重并保序
        found_unique: list[str] = []
        seen_found: set[str] = set()
        for term in found_terms:
            key = term.strip().lower()
            if key and key not in seen_found:
                seen_found.add(key)
                found_unique.append(term)

        matched_set = {
            term.strip().lower() for term in matched_terms if term.strip()
        }
        term_lookup = self._build_term_lookup(target_lang)

        lines = [
            "\n\nTerm Matching Signals (precomputed hints for comparison):",
            "Use this section to compare expected glossary/binance terms against translation output.",
            "Always verify with the actual translated text before final scoring.",
            "Signals with 'no expected translation in review glossary' are weak hints only,",
            "and cannot be used alone to fail.",
        ]

        # L1 强制覆盖说明
        if l1_matches:
            lines.append(
                "\n⚠️ L1 Glossary Override: Terms marked 'l1_forced' below were "
                "force-applied by the glossary system AFTER LLM translation. "
                "Their translated form is the glossary-mandated result. "
                "Do NOT flag these as 'untranslated' or 'wrong target language', "
                "even if the translation looks identical to the English source."
            )

        if found_unique:
            lines.append("\nFound terms from matching stage:")
            for term in found_unique[:40]:
                term_key = term.strip().lower()
                status = (
                    "matched_in_translation"
                    if term_key in matched_set
                    else "missing_in_translation"
                )

                # 判断是否为 L1 强制覆盖
                is_l1_forced = term_key in l1_lower_set

                term_info = term_lookup.get(term_key)
                if term_info:
                    term_name, expected, source = term_info
                    source_label = (
                        "official_glossary"
                        if source == "official"
                        else "binance_reference"
                    )
                    if is_l1_forced:
                        l1_translation = l1_matches.get(
                            term, l1_matches.get(term_key, expected)
                        )
                        lines.append(
                            f"- '{term_name}' ({source_label}) expected '{expected}' | "
                            f"signal=l1_forced (glossary override → '{l1_translation}')"
                        )
                    else:
                        lines.append(
                            f"- '{term_name}' ({source_label}) expected '{expected}' | "
                            f"signal={status}"
                        )
                else:
                    if is_l1_forced:
                        l1_translation = l1_matches.get(
                            term, l1_matches.get(term_key, "")
                        )
                        lines.append(
                            f"- '{term}' (l1_glossary) | "
                            f"signal=l1_forced (glossary override → '{l1_translation}')"
                        )
                    else:
                        lines.append(
                            f"- '{term}' (no expected translation in review glossary) | "
                            f"signal={status}"
                        )
        else:
            lines.append("\nFound terms from matching stage: none")

        if matched_set:
            matched_display = [
                term for term in found_unique if term.strip().lower() in matched_set
            ]
            if not matched_display:
                matched_display = sorted(matched_set)
            lines.append(
                "\nTerms already matched in translated text "
                "(from translation stage signals):"
            )
            for term in matched_display[:40]:
                lines.append(f"- '{term}'")
        else:
            lines.append(
                "\nTerms already matched in translated text "
                "(from translation stage signals): none"
            )

        return "\n".join(lines)

    def _build_prompt(
        self,
        source_text: str,
        translated_text: str,
        target_lang: str,
        source_text_2: str | None = None,
        glossary_terms_found: list[str] | None = None,
        glossary_terms_matched: list[str] | None = None,
        glossary_l1_direct_matches: dict[str, str] | None = None,
    ) -> str:
        """构建质量评审提示词"""
        target_lang_name = get_language_name(target_lang)
        glossary_reference = self._build_glossary_reference(target_lang)
        term_match_signals = self._build_term_match_signals(
            target_lang=target_lang,
            glossary_terms_found=glossary_terms_found,
            glossary_terms_matched=glossary_terms_matched,
            glossary_l1_direct_matches=glossary_l1_direct_matches,
        )

        # 构建源文本输入部分
        if source_text and source_text_2:
            source_section = (
                f"- **Source Language 1 (English):** {source_text}\n"
                f"- **Source Language 2 (Simplified Chinese):** {source_text_2}"
            )
        elif source_text:
            source_section = f"- **Source Language 1 (English):** {source_text}"
        else:
            source_section = (
                f"- **Source Language 1 (Simplified Chinese):** {source_text_2}"
            )

        return f"""### Role
You are a **Translation Quality Review Agent** for crypto product UI copy.

### Goal
Evaluate translation quality and output **PASS / FAIL** with detailed reasoning.

### Input
{source_section}
- **Translated text ({target_lang_name}):** {translated_text}
{glossary_reference}
{term_match_signals}

**Source Conflict Resolution Rule (CRITICAL — apply BEFORE any quality judgment):**
- If English and Chinese meanings **do NOT conflict** → Use **both combined** as reference
- If English and Chinese meanings **conflict** → **English is the SOLE reference. Ignore Chinese completely.**
- A translation that correctly conveys the English meaning is **CORRECT**, even if it contradicts the Chinese.

⚠️ COMMON MISTAKE: Do NOT penalize a translation that faithfully translates the English
but differs from the Chinese. Examples of EN/ZH conflicts where English prevails:
- EN "Max Drawdown Reached" vs ZH "保护止盈触发" → translation should mean "max drawdown reached"
- EN "Copy stopped" vs ZH "停止分润" → translation should mean "copy stopped"
- EN "Master Portfolio" vs ZH "带单交易" → translation should mean "master portfolio"

---

## Evaluation Process

### Step 1: Glossary Term Check (MANDATORY)

**For each term in the official glossary (if provided):**

0. If official glossary is empty for this target language:
   - Skip glossary gate
   - Continue to source + quality evaluation
   - Do NOT output glossary-absence failure reasons (e.g., "术语表缺失")

1. Check if term appears in either source (English or Chinese)
2. Verify translation matches glossary exactly:
   - ✅ Match → Continue
   - ❌ Mismatch → **HARD FAIL**
     - mark = 0
     - `{{"mark": 0, "failure_reason": "术语错误：[术语] 应为 [正确翻译]，实际为 [错误翻译]"}}`

### Step 2: Determine Source Reference (CRITICAL)

Compare English and Chinese sources:
- No conflict → Use both English + Chinese
- Conflict → **English is the SOLE reference. Completely disregard Chinese.**
  A translation matching English is CORRECT regardless of Chinese meaning.

### Step 3: Quality Evaluation

**Only if Steps 1-2 passed**

#### 3.1 Accuracy (35 points)
- Core meaning must match determined source reference
- Preserve all: placeholders, numbers, symbols, time info
- Synonymous wording is acceptable when no official glossary constraint applies
- **Hard Fail (mark = 0):**
  - Translation is untranslated or in the wrong target language
  - Core meaning contradiction/reversal
  - Missing/incorrect placeholder
  - Number/symbol corruption

#### 3.2 Binance Terminology (30 points)
- Secondary reference only (NOT mandatory)
- Penalty: -3 points per deviation
- NOT a Hard Fail by itself

#### 3.3 Fluency (20 points)
- Natural in target language
- Appropriate for UI context

#### 3.4 Style (15 points)
- Professional for crypto/finance
- Concise and user-friendly

---

## Scoring
- Range: 0–100
- **Weights:** Accuracy 35 + Terminology 30 + Fluency 20 + Style 15 = 100
- PASS: ≥ 95
- FAIL: < 95

### Hard Fail Guardrails (STRICT)
Set `mark=0` ONLY when at least one condition is true:
1. Official glossary mismatch (and official glossary exists for this target language)
2. Untranslated text or wrong target language
3. Core meaning contradiction/reversal
4. Placeholder/number/symbol corruption

Never set `mark=0` for wording preference, synonym choice, Binance-only deviation,
or weak hints like "no expected translation in review glossary" alone.

### L1 Glossary Override Rule
When Term Matching Signals show `signal=l1_forced`, the term was force-applied by the
glossary system after translation. The translated form is the glossary-mandated result.
Do NOT flag l1_forced terms as "untranslated" or "wrong target language", even if the
translation is identical to the English source (the glossary intentionally keeps it).

---

## Output Format

**PASS:**
```json
{{"mark": 97}}
```

**FAIL (minor):**
```json
{{"mark": 92, "failure_reason": "流畅度不足：支持进行交易 表达不自然"}}
```

**FAIL (Hard Fail):**
```json
{{"mark": 0, "failure_reason": "术语错误：Spot Trading 应为现货交易，实际为即时交易"}}
```

### Output Rules:
1. Return **ONLY** JSON object
2. `failure_reason` 用中文，不超过 20 字
3. 必须指出具体词/片段 + 问题类型
4. Hard Fail 时 mark = 0"""

    def build_review_messages(
        self,
        source_text: str,
        translated_text: str,
        target_lang: str,
        source_text_2: str | None = None,
        glossary_terms_found: list[str] | None = None,
        glossary_terms_matched: list[str] | None = None,
        glossary_l1_direct_matches: dict[str, str] | None = None,
    ) -> list[dict[str, str]]:
        """构建评审消息（system + user）"""
        prompt = self._build_prompt(
            source_text=source_text,
            translated_text=translated_text,
            target_lang=target_lang,
            source_text_2=source_text_2,
            glossary_terms_found=glossary_terms_found,
            glossary_terms_matched=glossary_terms_matched,
            glossary_l1_direct_matches=glossary_l1_direct_matches,
        )
        return [
            {"role": "system", "content": self.SYSTEM_PROMPT},
            {"role": "user", "content": prompt},
        ]

    def build_review_input_text(
        self,
        source_text: str,
        translated_text: str,
        target_lang: str,
        source_text_2: str | None = None,
        glossary_terms_found: list[str] | None = None,
        glossary_terms_matched: list[str] | None = None,
        glossary_l1_direct_matches: dict[str, str] | None = None,
    ) -> str:
        """构建调试用的模型输入文本"""
        messages = self.build_review_messages(
            source_text=source_text,
            translated_text=translated_text,
            target_lang=target_lang,
            source_text_2=source_text_2,
            glossary_terms_found=glossary_terms_found,
            glossary_terms_matched=glossary_terms_matched,
            glossary_l1_direct_matches=glossary_l1_direct_matches,
        )
        parts = []
        for message in messages:
            role = str(message.get("role", "")).upper()
            content = str(message.get("content", ""))
            parts.append(f"{role}:\n{content}")
        return "\n\n".join(parts)

    def _is_l1_false_positive(
        self,
        mark: int,
        failure_reason: str,
        glossary_l1_direct_matches: dict[str, str] | None,
    ) -> bool:
        """
        检测 L1 强制覆盖术语是否被误判为"未翻译"。

        当 mark=0 且 failure_reason 提到的术语是 L1 强制匹配时，
        说明模型忽略了 L1 Glossary Override 规则，应覆盖为通过。
        仅拦截"未翻译"类误判，不影响其他合法 Hard Fail。
        """
        if mark != 0 or not glossary_l1_direct_matches or not failure_reason:
            return False

        reason_lower = failure_reason.lower()

        # 未翻译/未本地化相关关键词
        untranslated_keywords = ["未翻译", "未本地化", "untranslated", "not translated"]
        has_untranslated_keyword = any(kw in reason_lower for kw in untranslated_keywords)

        # 也检查 "未X语化" 模式（如 "未越南语化"、"未日语化"）
        if not has_untranslated_keyword:
            has_untranslated_keyword = bool(re.search(r"未.{1,5}语化", failure_reason))

        if not has_untranslated_keyword:
            return False

        # 检查 failure_reason 中是否提到了 L1 强制覆盖的术语
        for term_en in glossary_l1_direct_matches:
            if term_en.lower() in reason_lower:
                return True

        return False

    def _parse_response(self, response: str) -> dict[str, Any]:
        """解析 LLM 响应，新格式: {mark, failure_reason?}"""
        json_match = re.search(r"\{[\s\S]*\}", response)
        if not json_match:
            logger.warning(
                f"[QualityReviewAgent._parse_response] 无法提取 JSON: {response[:200]}"
            )
            return {"mark": 0, "failure_reason": "解析评审响应失败"}

        try:
            parsed = json.loads(json_match.group())
            # 兼容新格式 (mark) 和旧格式 (overall_score)
            if "mark" not in parsed and "overall_score" in parsed:
                parsed["mark"] = parsed["overall_score"]
            return parsed
        except json.JSONDecodeError as e:
            logger.warning(f"[QualityReviewAgent._parse_response] JSON 解析失败: {e}")
            return {"mark": 0, "failure_reason": "解析评审响应失败"}

    async def run(
        self,
        source_text: str,
        translated_text: str,
        target_lang: str,
        source_text_2: str | None = None,
        glossary_terms_found: list[str] | None = None,
        glossary_terms_matched: list[str] | None = None,
        glossary_l1_direct_matches: dict[str, str] | None = None,
    ) -> QualityReviewResult:
        """
        执行质量评审

        Args:
            source_text: 源文本
            translated_text: 翻译文本
            target_lang: 目标语言代码

        Returns:
            QualityReviewResult 包含评审结果
        """
        logger.info(f"[QualityReviewAgent.run] 开始质量评审, target_lang={target_lang}")

        # 构建提示词
        messages = self.build_review_messages(
            source_text=source_text,
            translated_text=translated_text,
            target_lang=target_lang,
            source_text_2=source_text_2,
            glossary_terms_found=glossary_terms_found,
            glossary_terms_matched=glossary_terms_matched,
            glossary_l1_direct_matches=glossary_l1_direct_matches,
        )

        # 调用 LLM
        try:
            response = await self._call_llm(
                messages=messages,
                temperature=0.2,
            )
        except Exception as e:
            logger.error(f"[QualityReviewAgent.run] 评审失败: {e}")
            # 评审调用失败时默认通过，避免阻塞流程
            return QualityReviewResult(
                target_lang=target_lang,
                source_text=source_text,
                translated_text=translated_text,
                score=QualityScore(score=75),
                passed=True,
                feedback=f"评审调用失败: {e}",
                suggestions=[],
            )

        # 解析响应
        parsed = self._parse_response(response)

        # 构建评分（新格式只有 mark）
        mark = int(parsed.get("mark", 0))
        failure_reason = parsed.get("failure_reason", "")

        # L1 强制覆盖术语的防误判保护
        if self._is_l1_false_positive(mark, failure_reason, glossary_l1_direct_matches):
            logger.warning(
                f"[QualityReviewAgent.run] L1 强制覆盖术语被误判为未翻译，"
                f"覆盖评分: {failure_reason}"
            )
            mark = 100
            failure_reason = ""

        score = QualityScore(score=mark)

        # 判断是否通过
        passed = mark >= self.quality_threshold

        result = QualityReviewResult(
            target_lang=target_lang,
            source_text=source_text,
            translated_text=translated_text,
            score=score,
            passed=passed,
            feedback=failure_reason,
            suggestions=[failure_reason] if failure_reason else [],
        )

        logger.info(
            f"[QualityReviewAgent.run] 质量评审完成, target_lang={target_lang}, "
            f"score={score.score}, passed={passed}"
        )

        return result
