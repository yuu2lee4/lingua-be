"""
术语表服务

加载和管理术语表数据，支持 JSON 文件和 MySQL 数据库

Two-Tier Glossary System:
- Level 1 (Match Glossary): Direct translation lookup via MatchGlossaryService
- Level 2 (Business Glossary): AI-curated terms for prompt enrichment (this service)
"""

import json
import asyncio
from pathlib import Path
from functools import lru_cache
from datetime import datetime, timedelta

from app.logger import logger
from app.core.exceptions import GlossaryLoadError
from app.schemas.glossary import GlossaryTerm, Glossary


class GlossaryService:
    """
    术语表服务 (Business AI Glossary)

    This is Level 2 of the two-tier glossary system, providing
    AI-curated professional terms for prompt enrichment.

    For Level 1 (direct translation lookup), use MatchGlossaryService.
    """

    # 缓存 TTL（秒）
    CACHE_TTL = 3600  # 60 分钟

    def __init__(self):
        self._cache: dict[str, Glossary] = {}
        self._db_cache: Glossary | None = None
        self._db_cache_time: datetime | None = None
        self._db_available: bool = False

    def load_glossary(
        self,
        file_path: str | Path,
        max_entries: int | None = None,
        use_cache: bool = True,
    ) -> Glossary:
        """
        加载术语表（从 JSON 文件）

        格式: {"terms": [{"term_id": ..., "term_en": ..., "definition": ..., ...}]}

        Args:
            file_path: 术语表 JSON 文件路径
            max_entries: 最大条目数限制
            use_cache: 是否使用缓存

        Returns:
            Glossary 对象
        """
        path = Path(file_path)
        cache_key = str(path.absolute())

        # 检查缓存
        if use_cache and cache_key in self._cache:
            logger.info(f"[load_glossary] 使用缓存: {cache_key}")
            return self._cache[cache_key]

        if not path.exists():
            raise GlossaryLoadError(str(path), "文件不存在")

        try:
            with open(path, encoding="utf-8") as f:
                data = json.load(f)

            terms = []
            for i, item in enumerate(data.get("terms", [])):
                if max_entries and i >= max_entries:
                    break
                term = GlossaryTerm(
                    term_id=item.get("term_id", ""),
                    term_en=item.get("term_en", ""),
                    definition=item.get("definition", ""),
                    part_of_speech=item.get("part_of_speech", ""),
                    do_not_translate=item.get("do_not_translate", False),
                    translations=item.get("translations", {}),
                )
                terms.append(term)

            glossary = Glossary(terms=terms)
            glossary.build_lookup()

            # 缓存
            if use_cache:
                self._cache[cache_key] = glossary

            logger.info(f"[load_glossary] 加载完成，共 {len(terms)} 条术语")
            return glossary

        except json.JSONDecodeError as e:
            raise GlossaryLoadError(str(path), f"JSON 解析错误: {e}")
        except Exception as e:
            raise GlossaryLoadError(str(path), str(e))

    async def load_glossary_from_db(
        self,
        use_cache: bool = True,
        force_refresh: bool = False,
    ) -> Glossary:
        """
        从数据库加载术语表

        Args:
            use_cache: 是否使用缓存
            force_refresh: 是否强制刷新缓存

        Returns:
            Glossary 对象
        """
        # 检查缓存是否有效
        if (
            use_cache
            and not force_refresh
            and self._db_cache is not None
            and self._db_cache_time is not None
        ):
            cache_age = datetime.now() - self._db_cache_time
            if cache_age < timedelta(seconds=self.CACHE_TTL):
                logger.debug("[load_glossary_from_db] 使用内存缓存")
                return self._db_cache

        try:
            from app.repositories.glossary_repository import glossary_repository
            from app.db.connection import DatabasePool

            # 检查数据库是否可用
            if not DatabasePool.is_initialized():
                logger.warning("[load_glossary_from_db] 数据库未初始化，降级到文件加载")
                return self._fallback_to_file()

            # 从数据库加载
            term_responses = await glossary_repository.get_all_active_terms()

            terms = []
            for resp in term_responses:
                term = GlossaryTerm(
                    term_id=resp.term_id,
                    term_en=resp.term_en,
                    definition=resp.definition,
                    part_of_speech=resp.part_of_speech,
                    do_not_translate=resp.do_not_translate,
                    translations=resp.translations,
                )
                terms.append(term)

            glossary = Glossary(terms=terms)
            glossary.build_lookup()

            # 更新缓存
            if use_cache:
                self._db_cache = glossary
                self._db_cache_time = datetime.now()
                self._db_available = True

            logger.info(f"[load_glossary_from_db] 加载完成，共 {len(terms)} 条术语")
            return glossary

        except Exception as e:
            logger.error(f"[load_glossary_from_db] 数据库加载失败: {e}")
            self._db_available = False
            return self._fallback_to_file()

    def _fallback_to_file(self) -> Glossary:
        """降级到文件加载"""
        base_dir = Path(__file__).parent.parent.parent
        glossary_path = base_dir / "examples" / "glossary.json"

        if not glossary_path.exists():
            logger.warning(f"[_fallback_to_file] 默认术语表不存在: {glossary_path}")
            return Glossary()

        return self.load_glossary(glossary_path)

    def invalidate_db_cache(self) -> None:
        """使数据库缓存失效"""
        self._db_cache = None
        self._db_cache_time = None
        logger.info("[invalidate_db_cache] 数据库缓存已失效")

    def clear_cache(self) -> None:
        """清除所有缓存"""
        self._cache.clear()
        self._db_cache = None
        self._db_cache_time = None
        logger.info("[clear_cache] 术语表缓存已清除")

    def is_db_available(self) -> bool:
        """检查数据库是否可用"""
        return self._db_available

    async def warmup_cache(self) -> None:
        """预热缓存（应用启动时调用）"""
        try:
            await self.load_glossary_from_db(use_cache=True, force_refresh=True)
            logger.info("[warmup_cache] 缓存预热完成")
        except Exception as e:
            logger.warning(f"[warmup_cache] 缓存预热失败: {e}")

    # ============ Two-Tier Glossary Methods ============

    async def get_direct_matches(
        self,
        source_text: str,
        target_lang: str,
    ) -> dict[str, str]:
        """
        Get direct translation matches from Match Glossary (Level 1).

        This method delegates to MatchGlossaryService for direct lookups.

        Args:
            source_text: Source text to analyze
            target_lang: Target language code

        Returns:
            Dict of {term_en: translation} for matched terms
        """
        try:
            from app.services.match_glossary_service import match_glossary_service

            return await match_glossary_service.get_direct_matches(
                source_text, target_lang
            )
        except Exception as e:
            logger.warning(f"[get_direct_matches] Error: {e}")
            return {}

    async def get_business_terms_for_prompt(
        self,
        source_text: str,
        target_lang: str,
        exclude_terms: list[str] | None = None,
    ) -> list[GlossaryTerm]:
        """
        Get business glossary terms for prompt enrichment (Level 2).

        This is used by TranslationAgent to add context to the LLM prompt.
        Terms that were already matched by Level 1 can be excluded.

        Args:
            source_text: Source text to analyze
            target_lang: Target language code
            exclude_terms: List of term_en values to exclude (already matched)

        Returns:
            List of GlossaryTerm objects with definitions and translations
        """
        try:
            # Load business glossary from database
            glossary = await self.load_glossary_from_db()

            # Find terms in the text
            all_terms = glossary.find_terms_in_text(source_text)

            # Exclude already-matched terms
            if exclude_terms:
                exclude_set = set(t.lower() for t in exclude_terms)
                all_terms = [
                    t for t in all_terms
                    if t.term_en.lower() not in exclude_set
                ]

            # Filter to only terms that have the target language translation
            filtered_terms = []
            for term in all_terms:
                translation = term.get_translation(target_lang)
                if translation or term.do_not_translate:
                    filtered_terms.append(term)

            logger.debug(
                f"[get_business_terms_for_prompt] Found {len(filtered_terms)} "
                f"terms for prompt enrichment (excluded {len(exclude_terms or [])})"
            )

            return filtered_terms

        except Exception as e:
            logger.warning(f"[get_business_terms_for_prompt] Error: {e}")
            return []

    async def get_two_tier_glossary_data(
        self,
        source_text: str,
        target_lang: str,
    ) -> tuple[dict[str, str], list[GlossaryTerm]]:
        """
        Get both direct matches and business terms in one call.

        Merges curated glossary data with Binance glossary data:
        - L1: Curated matches take priority, Binance supplements
        - L2: Curated terms first, then Binance short terms (all excluded from L1)

        Args:
            source_text: Source text to analyze
            target_lang: Target language code

        Returns:
            Tuple of (direct_matches, business_terms)
            - direct_matches: Dict of {term_en: translation} for Level 1
            - business_terms: List of GlossaryTerm for Level 2 prompt enrichment
        """
        # Get Level 1: Curated direct matches
        direct_matches = await self.get_direct_matches(source_text, target_lang)

        # Get Level 2: Business terms (excluding already matched)
        exclude_terms = list(direct_matches.keys())
        business_terms = await self.get_business_terms_for_prompt(
            source_text, target_lang, exclude_terms
        )

        # 将 business_glossary 术语提升为硬匹配（与 match_glossary 同等强制替换）
        for term in business_terms:
            translation = term.get_translation(target_lang)
            if translation:
                direct_matches[term.term_en] = translation

        # L2 supplement: Binance matches demoted to L2 reference (not L1 forced replacement)
        try:
            from app.services.binance_glossary_service import binance_glossary_service

            # Binance direct matches → L2 参考（LLM 自主判断是否采用）
            binance_direct = binance_glossary_service.get_direct_matches(
                source_text, target_lang
            )
            curated_lower = {k.lower() for k in direct_matches}
            all_l2_lower = {t.term_en.lower() for t in business_terms}
            for term, trans in binance_direct.items():
                if term.lower() not in curated_lower and term.lower() not in all_l2_lower:
                    business_terms.append(
                        GlossaryTerm(
                            term_en=term,
                            translations={target_lang: trans},
                            source="binance.com",
                        )
                    )

            # Binance short terms (exclude L1 + all L2)
            all_exclude = exclude_terms + [t.term_en for t in business_terms]
            binance_terms = binance_glossary_service.get_prompt_terms(
                source_text, target_lang, all_exclude
            )
            business_terms = business_terms + binance_terms
        except Exception as e:
            logger.debug(f"[get_two_tier_glossary_data] Binance L2 skip: {e}")

        logger.info(
            f"[get_two_tier_glossary_data] Level 1 matches: {len(direct_matches)}, "
            f"Level 2 terms: {len(business_terms)}"
        )

        return direct_matches, business_terms


# 全局单例
glossary_service = GlossaryService()


@lru_cache(maxsize=1)
def get_default_glossary() -> Glossary:
    """
    获取默认术语表

    从 data/glossary.json 加载
    """
    from pathlib import Path

    base_dir = Path(__file__).parent.parent.parent
    glossary_path = base_dir / "examples" / "glossary.json"

    if not glossary_path.exists():
        logger.warning(f"[get_default_glossary] 默认术语表不存在: {glossary_path}")
        return Glossary()

    return glossary_service.load_glossary(glossary_path)


async def get_glossary_async() -> Glossary:
    """
    异步获取术语表

    优先从数据库加载，失败时降级到文件
    """
    return await glossary_service.load_glossary_from_db()
