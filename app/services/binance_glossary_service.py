"""
Binance 术语库服务

从 Binance 网站爬取的多语言 UI 术语，提供 L1 直接匹配和 L2 提示词增强。
融入现有两级术语表系统，Binance 数据补充但不覆盖人工维护数据。

数据特点：
- 短术语（1-4 词）: 行业术语，适合 L1 直接匹配 + L2 提示词增强
- 长 UI 字符串（5+ 词）: 翻译记忆 L1 匹配，不适合放入提示词
- 无 definition 和 part_of_speech 字段（来自 DOM/i18n 爬取）
"""

import json
import re
from pathlib import Path
from datetime import datetime, timedelta

from app.logger import logger
from app.schemas.glossary import GlossaryTerm, Glossary

# 默认数据文件路径
DEFAULT_DATA_PATH = (
    Path(__file__).parent.parent.parent
    / "data"
    / "binance_glossary"
    / "binance_glossary.json"
)

# 占位符模式: {n}, {amount}, ${value} 等
_PLACEHOLDER_PATTERN = re.compile(r"[{$]")
# 交易对模式: BTC/USDT, ETH/BTC 等
_TRADING_PAIR_PATTERN = re.compile(r"[A-Z]{2,5}/[A-Z]{2,5}")
# 小数价格模式: 0.001, 1.5 等
_DECIMAL_PRICE_PATTERN = re.compile(r"\b\d+\.\d+\b")


def _is_quality_term(term_en: str) -> bool:
    """
    判断术语是否满足 L2 质量过滤条件

    L2 只使用短术语（≤4 词）且满足质量标准

    Args:
        term_en: 英文术语

    Returns:
        是否满足质量标准
    """
    # 长度 > 2
    if len(term_en) <= 2:
        return False

    # 以字母开头
    if not term_en[0].isalpha():
        return False

    # 词数 ≤ 4
    words = term_en.split()
    if len(words) > 4:
        return False

    # 不含占位符
    if _PLACEHOLDER_PATTERN.search(term_en):
        return False

    # 不含交易对模式
    if _TRADING_PAIR_PATTERN.search(term_en):
        return False

    # 不含小数价格数据
    if _DECIMAL_PRICE_PATTERN.search(term_en):
        return False

    return True


class BinanceGlossaryService:
    """
    Binance 术语库服务 - 提供 L1 直接匹配 + L2 提示词增强

    L1: 全部术语，用于直接翻译匹配
    L2: 仅通过质量过滤的短术语（≤4 词），用于提示词增强
    """

    CACHE_TTL = 7200  # 2小时
    MAX_WORDS_FOR_L2 = 4  # L2 只使用 ≤4 词的术语
    MAX_TERMS_IN_PROMPT = 30  # 每次提示词最多包含的术语数

    def __init__(self):
        # L1 缓存: {term_en_lower: {lang_code: translation}}
        self._l1_cache: dict[str, dict[str, str]] = {}
        # L2 glossary: 仅短术语，用于 find_terms_in_text()
        self._l2_glossary: Glossary = Glossary()
        # 首词倒排索引: {first_word_lower: [term_en_lower, ...]}
        self._first_word_index: dict[str, list[str]] = {}
        # 加载状态
        self._loaded: bool = False
        self._load_time: datetime | None = None
        self._data_path: Path = DEFAULT_DATA_PATH

    @property
    def l1_count(self) -> int:
        """L1 术语数量"""
        return len(self._l1_cache)

    @property
    def l2_count(self) -> int:
        """L2 术语数量"""
        return len(self._l2_glossary.terms)

    async def load(self, file_path: Path | None = None) -> None:
        """
        从 JSON 文件加载术语数据，拆分为 L1 cache 和 L2 glossary

        Args:
            file_path: JSON 文件路径，默认使用 data/binance_glossary/binance_glossary.json
        """
        path = file_path or self._data_path

        if not path.exists():
            logger.warning(f"[BinanceGlossaryService.load] 文件不存在: {path}")
            return

        try:
            raw = path.read_text(encoding="utf-8").strip()
            if not raw:
                logger.warning(f"[BinanceGlossaryService.load] 文件为空: {path}")
                return

            data = json.loads(raw)

            terms_data = data.get("terms", [])
            if not terms_data:
                logger.warning("[BinanceGlossaryService.load] 术语数据为空")
                return

            l1_cache: dict[str, dict[str, str]] = {}
            l2_terms: list[GlossaryTerm] = []
            first_word_index: dict[str, list[str]] = {}

            for item in terms_data:
                term_en = item.get("term_en", "").strip()
                if not term_en:
                    continue

                translations = item.get("translations", {})
                if not translations:
                    continue

                term_lower = term_en.lower()

                # L1: 全部术语
                l1_cache[term_lower] = translations

                # 构建首词倒排索引（提取第一个纯字母 token 作为索引键）
                first_token = term_lower.split()[0] if term_lower.split() else ""
                alpha_match = re.match(r"[a-zA-Z]+", first_token)
                first_word = alpha_match.group() if alpha_match else first_token
                if first_word:
                    if first_word not in first_word_index:
                        first_word_index[first_word] = []
                    first_word_index[first_word].append(term_lower)

                # L2: 仅质量过滤通过的短术语
                if _is_quality_term(term_en):
                    l2_terms.append(
                        GlossaryTerm(
                            term_id=item.get("term_id", ""),
                            term_en=term_en,
                            translations=translations,
                            source="binance.com",
                        )
                    )

            self._l1_cache = l1_cache
            self._first_word_index = first_word_index
            self._l2_glossary = Glossary(terms=l2_terms)
            self._l2_glossary.build_lookup()
            self._loaded = True
            self._load_time = datetime.now()

            logger.info(
                f"[BinanceGlossaryService.load] 加载完成, "
                f"L1={len(l1_cache)}, L2={len(l2_terms)}"
            )

        except json.JSONDecodeError as e:
            logger.error(f"[BinanceGlossaryService.load] JSON 解析错误: {e}")
        except Exception as e:
            logger.error(f"[BinanceGlossaryService.load] 加载失败: {e}")

    def get_direct_matches(
        self,
        source_text: str,
        target_lang: str,
    ) -> dict[str, str]:
        """
        L1 匹配：从源文本中查找 Binance 术语的直接翻译

        使用首词倒排索引优化，避免遍历全部 16K 术语。

        Args:
            source_text: 源文本
            target_lang: 目标语言代码

        Returns:
            匹配的术语字典 {term_en: translation}
        """
        if not self._loaded:
            return {}

        matches: dict[str, str] = {}
        source_lower = source_text.lower()
        source_words = set(re.findall(r"[a-zA-Z]+", source_lower))

        # 通过首词索引缩小候选范围
        candidate_terms: set[str] = set()
        for word in source_words:
            word_lower = word.lower()
            if word_lower in self._first_word_index:
                candidate_terms.update(self._first_word_index[word_lower])

        # 对候选术语做词边界匹配
        for term_lower in candidate_terms:
            translation = self._l1_cache[term_lower].get(target_lang)
            if not translation:
                continue

            # 词边界匹配
            pattern = r"(?<![a-zA-Z0-9.])" + re.escape(term_lower) + r"(?![a-zA-Z0-9.])"
            match = re.search(pattern, source_lower)
            if match:
                # 从源文本中提取原始大小写形式
                start, end = match.start(), match.end()
                original_term = source_text[start:end]
                matches[original_term] = translation

        return matches

    def get_prompt_terms(
        self,
        source_text: str,
        target_lang: str,
        exclude_terms: list[str] | None = None,
        max_terms: int | None = None,
    ) -> list[GlossaryTerm]:
        """
        L2 提示词术语：从源文本中查找相关的 Binance 短术语

        Args:
            source_text: 源文本
            target_lang: 目标语言代码
            exclude_terms: 要排除的术语列表（已被 L1 匹配或人工维护术语覆盖）
            max_terms: 最大术语数量

        Returns:
            GlossaryTerm 列表
        """
        if not self._loaded:
            return []

        max_terms = max_terms or self.MAX_TERMS_IN_PROMPT

        # 查找文本中出现的 L2 术语
        found_terms = self._l2_glossary.find_terms_in_text(source_text)

        # 排除已匹配/已有的术语
        if exclude_terms:
            exclude_set = {t.lower() for t in exclude_terms}
            found_terms = [
                t for t in found_terms if t.term_en.lower() not in exclude_set
            ]

        # 过滤目标语言有翻译的术语
        filtered: list[GlossaryTerm] = []
        for term in found_terms:
            if term.translations.get(target_lang):
                filtered.append(term)

        # 按术语长度排序（短术语优先，更精确）
        filtered.sort(key=lambda t: len(t.term_en))

        return filtered[:max_terms]

    def get_l2_glossary(self) -> Glossary:
        """
        返回 L2 glossary 对象（供一致性评审合并用）

        Returns:
            Glossary 对象
        """
        return self._l2_glossary


# 全局单例
binance_glossary_service = BinanceGlossaryService()
