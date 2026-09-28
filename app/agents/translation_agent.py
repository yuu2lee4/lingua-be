"""
翻译 Agent

负责执行单个语言的翻译任务

Two-Tier Glossary System:
- Level 1 (Match Glossary): Direct translation lookup - terms are replaced directly in output
- Level 2 (Business Glossary): AI-curated terms for prompt enrichment
"""

import re
import time
from collections import Counter
from typing import Any

from app.agents.base import BaseAgent
from app.core.constants import get_language_name
from app.logger import logger
from app.schemas.glossary import Glossary, GlossaryTerm
from app.schemas.review import ReviewFeedback
from app.schemas.translation import TranslationItem


class TranslationAgent(BaseAgent):
    """
    翻译 Agent

    执行单个语言的翻译任务，支持两级术语表和评审反馈：
    - Level 1: Match Glossary - 直接替换翻译结果中的术语
    - Level 2: Business Glossary - 用于 prompt 上下文增强
    """

    agent_type = "translation"

    # 东亚语言（CJK）- 使用全角标点，文字间不加空格
    CJK_LANGUAGES = {"zh-CN", "zh-TW", "ja-JP", "ko-KR"}

    # 东南亚语言 - 使用全角标点，文字间不加空格
    SEA_LANGUAGES = {"th-TH", "vi-VN", "id-ID"}

    # 南亚语言 - 有各自的标点习惯
    SOUTH_ASIAN_LANGUAGES = {"hi-IN", "bn-BD"}

    # 阿拉伯语系 - RTL 语言，有自己的标点习惯
    ARABIC_LANGUAGES = {"ar"}

    # 法语 - 特殊标点规则（某些标点前需要空格）
    FRENCH_LANGUAGES = {"fr-FR"}

    # 西方语言 - 使用半角标点
    WESTERN_LANGUAGES = {
        "en-US",
        "de-DE",
        "es-ES",
        "pt-BR",
        "ru-RU",
        "uk-UA",
    }

    def __init__(
        self,
        target_lang: str,
        glossary: Glossary | None = None,
        use_two_tier_glossary: bool = True,
        **kwargs: Any,
    ):
        """
        初始化翻译 Agent

        Args:
            target_lang: 目标语言代码
            glossary: 术语表 (Business Glossary for Level 2)
            use_two_tier_glossary: 是否启用两级术语表系统
            **kwargs: 传递给基类的参数
        """
        super().__init__(**kwargs)
        self.target_lang = target_lang
        self.glossary = glossary or Glossary()
        self.use_two_tier_glossary = use_two_tier_glossary

    def _get_punctuation_rules(self) -> str:
        """
        获取目标语言的标点符号和空格处理规则

        Returns:
            标点符号和空格处理规则的提示词
        """
        lang = self.target_lang

        if lang in self.CJK_LANGUAGES:
            return """
Punctuation and Spacing Rules (IMPORTANT):
- Use fullwidth punctuation marks: ，。！？：；""''（）【】
- Do NOT add spaces between Chinese/Japanese/Korean characters
- Do NOT add spaces between CJK text and numbers (e.g., "第3步" not "第 3 步")
- Do NOT add spaces between CJK text and English words, EXCEPT for:
  * Technical terms (e.g., "使用 API 接口" - keep spaces around API)
  * Brand names and product names (e.g., "Bitcoin 钱包")
  * Coin/token symbols (e.g., "购买 BTC")
- Keep spaces within English phrases/terms (e.g., "Copy Trade" stays as is)
- Punctuation marks should NOT have spaces before or after them"""

        elif lang in self.SEA_LANGUAGES:
            if lang == "th-TH":
                return """
Punctuation and Spacing Rules (IMPORTANT):
- Thai uses spaces to separate words/phrases, but no spaces around punctuation
- Do NOT add spaces before punctuation marks
- Use appropriate Thai punctuation where applicable
- Keep English technical terms with their original spacing"""
            elif lang == "vi-VN":
                return """
Punctuation and Spacing Rules (IMPORTANT):
- Use standard punctuation marks: , . ! ? : ; " " ' ' ( )
- Add space after punctuation marks (not before)
- Vietnamese words are separated by spaces
- Keep English technical terms and brand names with their original format"""
            else:  # id-ID
                return """
Punctuation and Spacing Rules (IMPORTANT):
- Use standard punctuation marks: , . ! ? : ; " " ' ' ( )
- Add space after punctuation marks (not before)
- Keep English technical terms and brand names with their original format"""

        elif lang in self.SOUTH_ASIAN_LANGUAGES:
            return """
Punctuation and Spacing Rules (IMPORTANT):
- Use appropriate punctuation marks for the target language
- Add space after punctuation marks where appropriate
- Keep English technical terms, brand names, and symbols with original spacing"""

        elif lang in self.ARABIC_LANGUAGES:
            return """
Punctuation and Spacing Rules (IMPORTANT):
- Use Arabic punctuation marks where appropriate: ، ؛ ؟
- Text flows right-to-left, but numbers and English terms remain left-to-right
- Keep English technical terms, brand names, and symbols with original format
- Do NOT add unnecessary spaces around punctuation"""

        elif lang in self.FRENCH_LANGUAGES:
            return """
Punctuation and Spacing Rules (IMPORTANT):
- Add a non-breaking space BEFORE: ! ? : ; » (French typography rule)
- Add a space after: , . « and other punctuation
- Keep English technical terms and brand names with their original format"""

        else:  # Western languages
            return """
Punctuation and Spacing Rules (IMPORTANT):
- Use standard punctuation marks: , . ! ? : ; " " ' ' ( )
- Add space after punctuation marks, not before
- Keep English technical terms and brand names with their original format"""

    # 各语言本地交易所标准参考
    LOCAL_EXCHANGE_STANDARDS: dict[str, str] = {
        "vi-VN": """Reference: Binance VN, MEXC VN
- "More" → "Xem thêm"
- "Deposit" → "Nạp" | "Withdraw" → "Rút"
- "Executed" → "Đã khớp lệnh"
""",
        "ja-JP": """Reference: BitFlyer, Coincheck, GMO Coin
- "Deposit" → "入金" | "Withdraw" → "出金"
- "Executed" → "約定済み"
- "More" → "詳細" (for detail navigation) or "もっと見る" (for list expansion)
- Use です/ます polite form throughout
- Prefer kanji: カスタマイズ for "user manual settings"
- Use 最適化 only for "system auto-optimization / AI optimization"
- Use "入金" NOT "デポジット"
""",
        "ko-KR": """Reference: Upbit, Bithumb, Coinone
- "Deposit" → "입금" | "Withdraw" → "출금"
- "Executed" → "체결완료"
- "More" → "더보기"
- Use 존댓말 (polite form) throughout
""",
        "es-ES": """Reference: Binance, Bitso (LatAm), Bit2Me (Spain)
- "Deposit" → "Depositar" | "Withdraw" → "Retirar"
- "Executed" → "Ejecutada" (column header) / "Orden ejecutada" (status)
- "More" → "Ver más"
- Use formal "usted" form
""",
        "fr-FR": """Reference: Binance, Kraken, Paymium
- "Deposit" → "Déposer" | "Withdraw" → "Retirer"
- "Executed" → "Exécuté"
- "More" → "Voir plus"
""",
        "de-DE": """Reference: Binance, Kraken, Bitcoin.de
- "Deposit" → "Einzahlen" | "Withdraw" → "Auszahlen"
- "Executed" → "Ausgeführt"
- "More" → "Mehr anzeigen"
- Use formal "Sie" form
""",
        "pt-BR": """Reference: Binance, Mercado Bitcoin, Foxbit
- "Deposit" → "Depositar" | "Withdraw" → "Sacar"
- "Executed" → "Executada"
- "More" → "Ver mais"
- Brazilian Portuguese preferred
""",
        "ru-RU": """Reference: Binance, Garantex, Exmo
- "Deposit" → "Пополнить" | "Withdraw" → "Вывести"
- "Executed" → "Исполнено"
- "More" → "Показать ещё"
""",
        "ar": """Reference: Binance, Rain, BitOasis
- "Deposit" → "إيداع" | "Withdraw" → "سحب"
- "Executed" → "منفذ"
- "More" → "عرض المزيد"
- Use RTL-appropriate phrasing
""",
        "uk-UA": """Reference: Binance, Kuna, WhiteBIT
- "Deposit" → "Поповнити" | "Withdraw" → "Вивести"
- "Executed" → "Виконано"
- "More" → "Показати більше"
""",
        "id-ID": """Reference: Indodax, Tokocrypto, Pintu, TRIV
- "Deposit" → "Setor"
- "Withdraw" → "Tarik" (CTA/primary action) | "Penarikan" (records, status, system messages)
- "Executed" → "Tereksekusi"
- "More" → "Lihat selengkapnya"
""",
    }

    # 语言敬语/正式度要求
    FORMALITY_RULES: dict[str, str] = {
        "ja-JP": "Always use です/ます体 (polite form). Never use casual form.",
        "ko-KR": "Always use 존댓말 (polite form). Never use 반말.",
        "de-DE": 'Always use formal "Sie" form. Never use informal "du".',
        "es-ES": 'Always use formal "usted" form. Never use informal "tú".',
    }

    # 专业但平易的语言
    ACCESSIBLE_TONE_LANGS = {"vi-VN", "id-ID", "pt-BR"}

    # 占位符匹配: {name}, <tag>, </tag>, <br></br>
    _PLACEHOLDER_RE = re.compile(
        r"\{[\w.]+\}"           # {n}, {coin_full_name}, {amount.value}
        r"|</?[a-zA-Z][\w]*>"   # <b>, </b>, <link>, </link>, <br>
    )

    # 推理泄漏快速检测（判断是否需要清理）
    _REASONING_LEAK_QUICK_RE = re.compile(
        r"(?im)(^wait[,.\s]|^hmm[,.\s]|^let me\s|^no,\s+let|^actually[,.\s]|"
        r"let me reconsider|the feedback says)"
    )

    # 推理行匹配模式（逐行判断）
    _REASONING_LINE_RE = re.compile(
        r"(?i)"
        r"(^wait\b|^hmm\b|^let me\b|^no,\s|^actually\b|"
        r"^the\s+(?:\w+\s+){0,3}(?:is|are|was|were|means|says|should|has|could)\b|"
        r"^looking at\b|^that'?s too\b|^I\s+(?:should|need|think)\b|"
        r"let me reconsider|was flagged|could be misread|literally means|"
        r"the feedback says|"
        r'^"[^"]+"\s*[=:])'
    )

    def _get_local_exchange_standards(self) -> str:
        """
        获取目标语言的本地交易所标准参考

        Returns:
            本地交易所术语标准的提示词
        """
        standards = self.LOCAL_EXCHANGE_STANDARDS.get(self.target_lang)
        if standards:
            return f"\nLocal Exchange Standards:\n{standards}"
        return ""

    def _get_formality_rules(self) -> str:
        """
        获取目标语言的敬语/正式度规则

        Returns:
            敬语/正式度规则的提示词
        """
        lang = self.target_lang
        rule = self.FORMALITY_RULES.get(lang)
        if rule:
            return f"\nFormality: {rule}"
        if lang in self.ACCESSIBLE_TONE_LANGS:
            return "\nFormality: Professional but accessible. Avoid overly formal phrasing that sounds unnatural."
        return ""

    def _build_glossary_section(self, glossary_terms: list[GlossaryTerm]) -> str:
        """
        构建术语表提示词部分 (Level 2: Business Glossary + Binance Reference)

        区分人工维护术语和 Binance 参考术语，分区展示
        """
        if not glossary_terms:
            return ""

        curated_lines: list[str] = []
        binance_lines: list[str] = []

        for entry in glossary_terms:
            if entry.do_not_translate:
                line = (
                    f"- '{entry.term_en}' -> Keep as "
                    f"'{entry.term_en}' (Do Not Translate)"
                )
            else:
                expected = entry.get_translation(self.target_lang)
                if expected:
                    line = f"- '{entry.term_en}' -> '{expected}'"
                else:
                    continue

            if entry.definition:
                line += f" | Definition: {entry.definition}"

            if entry.source == "binance.com":
                binance_lines.append(line)
            else:
                curated_lines.append(line)

        sections: list[str] = []

        if curated_lines:
            sections.append(
                "\n\nGlossary (use these exact translations):\n"
                + "\n".join(curated_lines)
            )

        if binance_lines:
            sections.append(
                "\n\nBinance Exchange Reference Terminology "
                "(prefer these for crypto exchange UI):\n" + "\n".join(binance_lines)
            )

        return "".join(sections)

    def _build_prompt(
        self,
        source_text: str,
        glossary_terms: list[GlossaryTerm],
        feedback: ReviewFeedback | None = None,
        key: str | None = None,
        source_text_2: str | None = None,
    ) -> str:
        """
        构建翻译提示词

        采用 UI-First 翻译策略，匹配本地交易所标准

        Args:
            source_text: 源文本
            glossary_terms: 相关术语 (Level 2: Business Glossary terms)
            feedback: 评审反馈（用于重新翻译）
            key: 文本标识键，可提供翻译语境信息

        Returns:
            完整提示词
        """
        target_lang_name = get_language_name(self.target_lang)
        glossary_section = self._build_glossary_section(glossary_terms)
        punctuation_rules = self._get_punctuation_rules()
        local_standards = self._get_local_exchange_standards()
        formality_rules = self._get_formality_rules()

        # 构建语境信息部分
        context_hint = ""
        if key:
            context_hint = f"\nContext Key: '{key}' (This key may provide hints about the text's purpose, location, or domain. Use it to inform your translation choices.)\n"

        prompt = f"""Translating product UI text from English/Simplified Chinese to {target_lang_name}.
Priority: Glossary compliance > Source accuracy > Local exchange conventions > UI clarity.{context_hint}

## Step 1: Glossary Compliance (MANDATORY - Highest Priority)
**Check glossary FIRST before any translation decision.**
- If a term exists in the glossary → **MUST use the exact glossary translation**
- No paraphrasing, no alternative translations for glossary terms.
{glossary_section}

## Step 2: Source Language Conflict Resolution

a) **No conflict** (English and Chinese convey same meaning):
   - Translate based on combined understanding of both sources

b) **Conflict exists** (English and Chinese differ):
   - **Prioritize English source**
   - Ignore conflicting Chinese content

## Step 3: Preserve Technical Elements
- Keep ALL placeholders intact: {{{{n}}}}, {{{{amount}}}}, {{{{symbol}}}}, {{{{reason}}}}, etc.
- Preserve numbers, symbols, and formatting exactly

## Step 4: Follow Local Exchange Standards
Reference major local exchanges to match user expectations.
{local_standards}

## Step 5: Apply UI-First Translation Principles

**Action Buttons** (clear and concise):
- Use established local action verbs
- Match local exchange button text length
- Clarity > extreme brevity

**Status Labels** (professional terminology):
- Use industry-standard trading terms
- Match local exchange status displays

**Descriptions/Tooltips** (natural phrasing):
- Complete phrases for clarity
- Natural sentence flow

## Step 6: Language-Specific Rules
{punctuation_rules}
{formality_rules}

Output: Return ONLY the translated text, no explanations."""

        # 如果有评审反馈，添加改进指导
        if feedback:
            prompt += "\n\n--- Previous Translation Feedback ---"

            # 展示历史重试记录（如果有多轮重试）
            if feedback.history:
                for i, attempt in enumerate(feedback.history, 1):
                    prompt += f"\n\n[Attempt {i}]"
                    prompt += f"\nTranslation: {attempt.get('translation', '')}"
                    prompt += f"\nFeedback: {attempt.get('feedback', '')}"
                prompt += f"\n\n[Attempt {len(feedback.history) + 1} - Latest]"

            prompt += f"\nOriginal translation: {feedback.original_translation}"

            if feedback.quality_feedback:
                prompt += f"\nQuality feedback: {feedback.quality_feedback}"

            if feedback.consistency_feedback:
                prompt += f"\nConsistency feedback: {feedback.consistency_feedback}"

            if feedback.suggestions:
                prompt += "\nSuggestions for improvement:"
                for suggestion in feedback.suggestions:
                    prompt += f"\n- {suggestion}"

            prompt += (
                "\n\nPlease provide an improved translation based on the feedback."
            )

        if source_text and source_text_2:
            # 双源：英文 + 中文
            prompt += f"\n\nSource text (English):\n{source_text}"
            prompt += f"\n\nSource text (Simplified Chinese):\n{source_text_2}"
            prompt += (
                "\n\nUse both source texts for context. "
                "When the English and Chinese meanings conflict, "
                "**prioritize the English text** as the authoritative source of meaning. "
                "The Chinese text provides supplementary context."
                "\n\nExamples:"
                '\n- English: "Futures Trading Bot PnL" / Chinese: "网格盈亏" '
                "→ Conflict: follow English meaning"
                '\n- English: "Start Price" / Chinese: "起始价格" '
                "→ No conflict: translate with combined understanding"
            )
        elif source_text:
            # 仅英文源
            prompt += f"\n\nText to translate:\n{source_text}"
        elif source_text_2:
            # 仅中文源
            prompt += f"\n\nSource text (Simplified Chinese):\n{source_text_2}"
            prompt += "\n\nTranslate the above Chinese text to the target language."

        # 严格输出约束（放在末尾确保模型最后看到）
        prompt += (
            "\n\n[OUTPUT RULE] Respond with the translated text ONLY — "
            "no reasoning, no alternatives, no commentary."
        )

        return prompt

    def _apply_direct_matches(
        self,
        translated_text: str,
        direct_matches: dict[str, str],
        source_text: str,
    ) -> str:
        """
        Apply Level 1 direct matches to the translated text.

        Replaces occurrences of source terms with their direct translations.

        Args:
            translated_text: LLM-generated translation
            direct_matches: Dict of {term_en: translation} from Match Glossary
            source_text: Original source text

        Returns:
            Translation with direct matches applied
        """
        if not direct_matches:
            return translated_text

        result = translated_text

        # Sort by length (longest first) to handle overlapping terms
        sorted_terms = sorted(direct_matches.keys(), key=len, reverse=True)

        for term_en in sorted_terms:
            expected_translation = direct_matches[term_en]

            # Check if the term appears in the source text
            # and if the expected translation is NOT already in the result
            term_pattern = re.compile(
                r"(?<![a-zA-Z0-9.])" + re.escape(term_en) + r"(?![a-zA-Z0-9.])", re.IGNORECASE
            )

            if term_pattern.search(source_text):
                # The term was in the source text
                # Check if the LLM already used the correct translation
                if expected_translation.lower() not in result.lower():
                    # Try to find what the LLM might have translated the term to
                    # and replace it with the expected translation
                    # This is a heuristic - if the English term appears in output, replace it
                    if term_pattern.search(result):
                        result = term_pattern.sub(expected_translation, result)
                        logger.debug(
                            f"[_apply_direct_matches] Replaced '{term_en}' "
                            f"with '{expected_translation}'"
                        )

        return result

    @staticmethod
    def _validate_placeholders(
        source_text: str,
        translated_text: str,
    ) -> list[str]:
        """
        校验翻译结果中占位符和 HTML 标签的完整性

        Args:
            source_text: 源文本
            translated_text: 翻译结果

        Returns:
            占位符问题列表，空列表表示无问题
        """
        source_holders = TranslationAgent._PLACEHOLDER_RE.findall(source_text)
        if not source_holders:
            return []

        translated_holders = TranslationAgent._PLACEHOLDER_RE.findall(translated_text)

        # 用计数比较，允许同一占位符出现多次
        source_counts = Counter(source_holders)
        translated_counts = Counter(translated_holders)

        issues: list[str] = []
        for ph, count in source_counts.items():
            t_count = translated_counts.get(ph, 0)
            if t_count == 0:
                issues.append(f"Missing placeholder: {ph}")
            elif t_count < count:
                issues.append(f"Placeholder count mismatch: {ph} (expected {count}, got {t_count})")

        for ph, count in translated_counts.items():
            if ph not in source_counts:
                issues.append(f"Unexpected placeholder: {ph}")

        return issues

    def _is_reasoning_line(self, line: str) -> bool:
        """判断一行是否为 LLM 推理泄漏"""
        stripped = line.strip()
        if not stripped:
            return False
        return bool(self._REASONING_LINE_RE.search(stripped))

    def _clean_translation_output(self, text: str) -> str:
        """
        清理 LLM 输出中的推理泄漏

        当模型在翻译（尤其是重试）时输出思考过程
        （如 "Wait, let me reconsider..."），提取最终翻译结果。
        """
        text = text.strip()

        # 快速检查：无推理特征则直接返回
        if not self._REASONING_LEAK_QUICK_RE.search(text):
            return text

        logger.warning(
            f"[_clean_translation_output] 检测到推理泄漏, "
            f"target_lang={self.target_lang}, output_len={len(text)}"
        )

        # 按段落分割（空行分隔）
        paragraphs = re.split(r"\n\s*\n", text)
        clean_paragraphs: list[str] = []

        for para in paragraphs:
            para = para.strip()
            if not para:
                continue
            # 段落中任意一行是推理则整段跳过
            lines = para.split("\n")
            has_reasoning = any(
                self._is_reasoning_line(line) for line in lines if line.strip()
            )
            if not has_reasoning:
                clean_paragraphs.append(para)

        if clean_paragraphs:
            # 返回最后一个干净段落（模型的最终翻译）
            result = clean_paragraphs[-1].strip()
            logger.info(
                f"[_clean_translation_output] 已清理推理泄漏, "
                f"原始长度={len(text)}, 清理后长度={len(result)}"
            )
            return result

        # 兜底：逐行过滤，取最后一个干净行
        all_lines = text.split("\n")
        clean_lines = [
            line.strip()
            for line in all_lines
            if line.strip() and not self._is_reasoning_line(line)
        ]
        if clean_lines:
            return clean_lines[-1]

        # 无法清理，返回原文（由质量评审捕获）
        logger.error(
            f"[_clean_translation_output] 无法提取翻译结果, "
            f"target_lang={self.target_lang}"
        )
        return text

    async def _get_two_tier_glossary_data(
        self,
        source_text: str,
    ) -> tuple[dict[str, str], list[GlossaryTerm]]:
        """
        Get both direct matches (Level 1) and business terms (Level 2).

        Args:
            source_text: Source text to analyze

        Returns:
            Tuple of (direct_matches, business_terms)
        """
        try:
            from app.services.glossary_service import glossary_service

            return await glossary_service.get_two_tier_glossary_data(
                source_text, self.target_lang
            )
        except Exception as e:
            logger.warning(f"[_get_two_tier_glossary_data] Error: {e}")
            # Fall back to traditional single-tier approach
            return {}, self.glossary.find_terms_in_text(source_text)

    async def run(
        self,
        source_text: str,
        feedback: ReviewFeedback | None = None,
        key: str | None = None,
        source_text_2: str | None = None,
    ) -> TranslationItem:
        """
        执行翻译

        Two-Tier Glossary Flow:
        1. Get direct matches from Match Glossary (Level 1)
        2. Get business terms for prompt enrichment (Level 2)
        3. Build prompt with Level 2 terms only (including key for context)
        4. Call LLM for translation
        5. Apply Level 1 direct matches to output

        Args:
            source_text: 源文本
            feedback: 评审反馈（用于重新翻译）
            key: 文本标识键，可提供翻译语境信息

        Returns:
            TranslationItem 包含翻译结果
        """
        start_time = time.perf_counter()

        # Initialize tracking variables
        direct_matches: dict[str, str] = {}
        glossary_terms: list[GlossaryTerm] = []

        # 术语匹配仅在有英文源文本时执行（术语库基于 term_en）
        if source_text:
            if self.use_two_tier_glossary:
                # Step 1 & 2: Get two-tier glossary data
                direct_matches, glossary_terms = await self._get_two_tier_glossary_data(
                    source_text
                )
                logger.info(
                    f"[TranslationAgent.run] Two-tier glossary: "
                    f"Level 1 matches={len(direct_matches)}, "
                    f"Level 2 terms={len(glossary_terms)}"
                )
            else:
                # Fall back to traditional single-tier approach
                glossary_terms = self.glossary.find_terms_in_text(source_text)

        terms_found = list(direct_matches.keys()) + [t.term_en for t in glossary_terms]

        logger.info(
            f"[TranslationAgent.run] 开始翻译, target_lang={self.target_lang}, "
            f"text_len={len(source_text)}, terms_found={len(terms_found)}, key={key}"
        )

        # Step 3: Build prompt with Level 2 terms only (including key for context)
        prompt = self._build_prompt(
            source_text, glossary_terms, feedback, key, source_text_2
        )

        # Step 4: Call LLM
        try:
            translated_text = await self._call_llm(
                messages=[
                    {
                        "role": "system",
                        "content": (
                            "You are a product UX translator for cryptocurrency exchange platforms, "
                            "specializing in clear, scannable UI copy that matches local market standards."
                        ),
                    },
                    {"role": "user", "content": prompt},
                ],
                temperature=0.3,
            )
        except Exception as e:
            logger.error(f"[TranslationAgent.run] 翻译失败: {e}")
            translated_text = f"[ERROR: {e}]"

        # Step 4.5: 清理推理泄漏
        if not translated_text.startswith("[ERROR:"):
            translated_text = self._clean_translation_output(translated_text)

        # Step 5: Apply Level 1 direct matches to output
        if direct_matches and not translated_text.startswith("[ERROR:"):
            original_translation = translated_text
            translated_text = self._apply_direct_matches(
                translated_text, direct_matches, source_text
            )
            if translated_text != original_translation:
                logger.debug(
                    "[TranslationAgent.run] Applied direct matches to translation"
                )

        # Step 6: 占位符完整性校验
        placeholder_issues: list[str] = []
        if not translated_text.startswith("[ERROR:"):
            ph_source = source_text or source_text_2 or ""
            if ph_source:
                placeholder_issues = self._validate_placeholders(
                    ph_source, translated_text
                )
                if placeholder_issues:
                    logger.warning(
                        f"[TranslationAgent.run] 占位符校验问题, "
                        f"target_lang={self.target_lang}, "
                        f"issues={placeholder_issues}"
                    )

        latency_ms = (time.perf_counter() - start_time) * 1000

        # Check term matching in final output
        terms_matched = []

        # Check Level 1 (direct matches)
        for term_en, expected in direct_matches.items():
            if expected.lower() in translated_text.lower():
                terms_matched.append(term_en)

        # Check Level 2 (business terms)
        for term in glossary_terms:
            expected = term.get_translation(self.target_lang)
            if expected and expected.lower() in translated_text.lower():
                if term.term_en not in terms_matched:
                    terms_matched.append(term.term_en)

        result = TranslationItem(
            target_lang=self.target_lang,
            translated_text=translated_text,
            latency_ms=latency_ms,
            glossary_terms_found=terms_found,
            glossary_terms_matched=terms_matched,
            glossary_l1_direct_matches=direct_matches,
            retry_count=1 if feedback else 0,
            placeholder_issues=placeholder_issues,
        )

        logger.info(
            f"[TranslationAgent.run] 翻译完成, target_lang={self.target_lang}, "
            f"latency_ms={latency_ms:.2f}, "
            f"terms_matched={len(terms_matched)}/{len(terms_found)}, "
            f"placeholder_issues={len(placeholder_issues)}"
        )

        return result
