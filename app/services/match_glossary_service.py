"""
匹配术语库服务 (Match Glossary Service)

这是两级术语库系统的 Level 1，提供直接翻译查找功能。
用于翻译过程中的直接替换，确保一致的术语翻译。

数据源:
- 主要从 examples/glossary.yaml 加载
- 也可以通过 API 从翻译反馈中更新

Tables:
- match_glossary_terms: 匹配术语主表
"""

import re
import hashlib
from pathlib import Path
from datetime import datetime, timedelta

import yaml

from app.db.connection import DatabasePool
from app.logger import logger
from app.utils.glossary_columns import (
    TRANSLATION_COLUMNS,
    COLUMN_TO_LANG_CODE,
    extract_translations,
    build_translation_columns,
)


# 默认 YAML 术语表路径
DEFAULT_YAML_PATH = Path(__file__).parent.parent.parent / "examples" / "glossary.yaml"


def _generate_term_id(term_en: str) -> str:
    """生成术语 ID（基于英文术语的 MD5 哈希）"""
    return hashlib.md5(term_en.lower().encode()).hexdigest()[:16]


class MatchGlossaryService:
    """
    匹配术语库服务 (Level 1)

    提供直接翻译查找，用于翻译过程中的术语替换。
    支持数据库和内存缓存两种模式。
    """

    # 缓存 TTL（秒）
    CACHE_TTL = 3600  # 60 分钟

    def __init__(self):
        # 内存缓存: {term_en_lower: {lang_code: translation}}
        self._cache: dict[str, dict[str, str]] = {}
        self._cache_time: datetime | None = None
        self._db_available: bool = False

    # ============ 缓存管理 ============

    def invalidate_cache(self) -> None:
        """使缓存失效"""
        self._cache.clear()
        self._cache_time = None
        logger.info("[MatchGlossaryService.invalidate_cache] 缓存已失效")

    def _is_cache_valid(self) -> bool:
        """检查缓存是否有效"""
        if not self._cache or not self._cache_time:
            return False
        cache_age = datetime.now() - self._cache_time
        return cache_age < timedelta(seconds=self.CACHE_TTL)

    async def warmup_cache(self) -> None:
        """
        预热缓存（应用启动时调用）

        从数据库加载所有匹配术语到内存
        """
        try:
            await self._load_all_to_cache()
            logger.info(
                f"[MatchGlossaryService.warmup_cache] 缓存预热完成, "
                f"共 {len(self._cache)} 条术语"
            )
        except Exception as e:
            logger.warning(f"[MatchGlossaryService.warmup_cache] 缓存预热失败: {e}")

    async def _load_all_to_cache(self) -> None:
        """从数据库加载所有术语到缓存"""
        if not DatabasePool.is_initialized():
            logger.warning("[MatchGlossaryService._load_all_to_cache] 数据库未初始化")
            return

        select_columns = ", ".join(["term_en", *TRANSLATION_COLUMNS])
        query = """
            SELECT {columns}
            FROM match_glossary_terms
            WHERE status = 'active'
        """.format(columns=select_columns)
        rows = await DatabasePool.fetch_all(query)

        self._cache.clear()
        for row in rows:
            term_en_lower = row["term_en"].lower()
            translations = extract_translations(row)
            if translations:
                self._cache[term_en_lower] = translations

        self._cache_time = datetime.now()
        self._db_available = True

    async def _ensure_cache_loaded(self) -> None:
        """确保缓存已加载"""
        if not self._is_cache_valid():
            await self._load_all_to_cache()

    # ============ 查找接口 ============

    async def lookup_translation(
        self,
        term_en: str,
        target_lang: str,
    ) -> str | None:
        """
        查找单个术语的翻译

        Args:
            term_en: 英文术语
            target_lang: 目标语言代码

        Returns:
            翻译结果，如果未找到则返回 None
        """
        await self._ensure_cache_loaded()

        term_lower = term_en.lower()
        if term_lower in self._cache:
            return self._cache[term_lower].get(target_lang)

        return None

    async def get_direct_matches(
        self,
        source_text: str,
        target_lang: str,
    ) -> dict[str, str]:
        """
        从源文本中查找所有匹配的术语及其翻译

        Args:
            source_text: 源文本
            target_lang: 目标语言代码

        Returns:
            匹配的术语字典 {term_en: translation}
        """
        await self._ensure_cache_loaded()

        matches: dict[str, str] = {}
        source_lower = source_text.lower()

        for term_lower, translations in self._cache.items():
            # 检查术语是否出现在源文本中（词边界匹配）
            # 使用正则确保是完整词匹配，而不是部分匹配
            pattern = r'(?<![a-zA-Z0-9.])' + re.escape(term_lower) + r'(?![a-zA-Z0-9.])'
            if re.search(pattern, source_lower, re.IGNORECASE):
                translation = translations.get(target_lang)
                if translation:
                    # 保留原始大小写形式
                    # 从缓存中找回原始术语
                    original_term = self._find_original_term(term_lower, source_text)
                    matches[original_term] = translation

        logger.debug(
            f"[MatchGlossaryService.get_direct_matches] "
            f"Found {len(matches)} matches for target_lang={target_lang}"
        )

        return matches

    def _find_original_term(self, term_lower: str, source_text: str) -> str:
        """
        从源文本中找到术语的原始大小写形式

        Args:
            term_lower: 小写术语
            source_text: 源文本

        Returns:
            原始大小写形式的术语
        """
        pattern = r'(?<![a-zA-Z0-9.])(' + re.escape(term_lower) + r')(?![a-zA-Z0-9.])'
        match = re.search(pattern, source_text, re.IGNORECASE)
        if match:
            return match.group(1)
        return term_lower

    # ============ 写入接口 ============

    async def upsert_translations_batch(
        self,
        term_en: str,
        translations: dict[str, str],
        source: str = "imported",
    ) -> bool:
        """
        批量插入或更新术语翻译

        Args:
            term_en: 英文术语
            translations: 翻译字典 {lang_code: translation}
            source: 来源标识

        Returns:
            是否成功
        """
        if not DatabasePool.is_initialized():
            logger.warning(
                "[MatchGlossaryService.upsert_translations_batch] 数据库未初始化"
            )
            return False

        term_id = _generate_term_id(term_en)

        try:
            translation_columns = build_translation_columns(translations)
            translation_keys = list(translation_columns.keys())

            insert_columns = [
                "term_id",
                "term_en",
                "source",
                "status",
                *translation_keys,
            ]
            insert_values = [
                term_id,
                term_en,
                source,
                "active",
                *[translation_columns[k] for k in translation_keys],
            ]
            placeholders = ", ".join(["%s"] * len(insert_columns))
            update_parts = [
                "term_en = VALUES(term_en)",
                "source = VALUES(source)",
                "status = 'active'",
            ]
            update_parts.extend([f"{col} = VALUES({col})" for col in translation_keys])

            # 插入或更新术语主表
            term_query = f"""
                INSERT INTO match_glossary_terms ({", ".join(insert_columns)})
                VALUES ({placeholders})
                ON DUPLICATE KEY UPDATE {", ".join(update_parts)}
            """
            await DatabasePool.execute(term_query, tuple(insert_values))

            # 更新缓存
            term_lower = term_en.lower()
            if term_lower not in self._cache:
                self._cache[term_lower] = {}
            if translation_columns:
                filtered = {
                    COLUMN_TO_LANG_CODE[column]: value
                    for column, value in translation_columns.items()
                    if column in COLUMN_TO_LANG_CODE
                }
                self._cache[term_lower].update(filtered)

            logger.info(
                f"[MatchGlossaryService.upsert_translations_batch] "
                f"Updated term: {term_en} with {len(translations)} translations"
            )
            return True

        except Exception as e:
            logger.error(
                f"[MatchGlossaryService.upsert_translations_batch] Error: {e}"
            )
            return False

    # ============ 初始化 ============

    async def initialize_from_yaml(
        self,
        yaml_path: Path | None = None,
    ) -> tuple[int, int, list[str]]:
        """
        从 YAML 文件初始化匹配术语库

        仅当 match_glossary_terms 表为空时执行导入

        Args:
            yaml_path: YAML 文件路径，默认使用 examples/glossary.yaml

        Returns:
            (导入成功数, 跳过数, 错误列表)
        """
        if not DatabasePool.is_initialized():
            logger.warning(
                "[MatchGlossaryService.initialize_from_yaml] 数据库未初始化"
            )
            return 0, 0, ["数据库未初始化"]

        # 检查表是否为空
        count_query = "SELECT COUNT(*) as total FROM match_glossary_terms"
        result = await DatabasePool.fetch_one(count_query)
        if result and result["total"] > 0:
            logger.info(
                "[MatchGlossaryService.initialize_from_yaml] "
                "术语表非空，跳过初始化"
            )
            return 0, 0, []

        # 确定文件路径
        file_path = yaml_path or DEFAULT_YAML_PATH
        if not file_path.exists():
            logger.warning(
                f"[MatchGlossaryService.initialize_from_yaml] "
                f"YAML 文件不存在: {file_path}"
            )
            return 0, 0, [f"文件不存在: {file_path}"]

        # 读取 YAML 文件
        try:
            with open(file_path, "r", encoding="utf-8") as f:
                data = yaml.safe_load(f)
        except yaml.YAMLError as e:
            logger.error(
                f"[MatchGlossaryService.initialize_from_yaml] YAML 解析失败: {e}"
            )
            return 0, 0, [f"YAML 解析失败: {e}"]

        if not data or not isinstance(data, dict):
            logger.warning(
                "[MatchGlossaryService.initialize_from_yaml] YAML 文件为空或格式错误"
            )
            return 0, 0, []

        # 导入术语
        imported = 0
        skipped = 0
        errors: list[str] = []

        for term_en, translations in data.items():
            if not isinstance(translations, dict):
                skipped += 1
                continue

            try:
                success = await self.upsert_translations_batch(
                    term_en=str(term_en),
                    translations={k: str(v) for k, v in translations.items()},
                    source="imported",
                )
                if success:
                    imported += 1
                else:
                    skipped += 1
            except Exception as e:
                errors.append(f"{term_en}: {str(e)}")

        logger.info(
            f"[MatchGlossaryService.initialize_from_yaml] 初始化完成: "
            f"导入={imported}, 跳过={skipped}, 错误={len(errors)}"
        )

        return imported, skipped, errors

    async def count_terms(self) -> int:
        """
        获取术语总数

        Returns:
            术语总数
        """
        if not DatabasePool.is_initialized():
            return 0

        query = "SELECT COUNT(*) as total FROM match_glossary_terms WHERE status = 'active'"
        result = await DatabasePool.fetch_one(query)
        return result["total"] if result else 0

    async def is_empty(self) -> bool:
        """
        检查术语表是否为空

        Returns:
            是否为空
        """
        count = await self.count_terms()
        return count == 0


# 全局单例
match_glossary_service = MatchGlossaryService()
