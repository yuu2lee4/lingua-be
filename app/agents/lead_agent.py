"""
Lead Agent - 翻译流程编排器

负责协调翻译、质量评审和一致性评审的完整流程

流程：
1. 并行执行多语言翻译
2. 并行执行质量评审
3. 执行一致性评审（按语言对循环组合）
4. 对未通过的翻译进行重试
"""

import asyncio
import time
from collections.abc import Awaitable, Callable

from app.agents.base import BaseAgent
from app.agents.review.consistency_agent import ConsistencyReviewAgent
from app.agents.review.quality_agent import QualityReviewAgent
from app.agents.translation_agent import TranslationAgent
from app.clients.llm_client import UnifiedLLMClient
from app.core.constants import MAX_RETRIES, QUALITY_THRESHOLD, get_language_name
from app.logger import logger
from app.schemas.glossary import Glossary, GlossaryTerm
from app.schemas.review import ReviewFeedback
from app.schemas.translation import (
    ConsistencyPairResult,
    TranslationItem,
    TranslationRequest,
    TranslationResponse,
)

# 进度回调类型: (phase, current_lang, completed_langs, consistency_pair, completed_pairs)
ProgressCallback = Callable[[str, str | None, int, str | None, int], Awaitable[None]]


class LeadAgent(BaseAgent):
    """
    Lead Agent - 翻译流程编排器

    流程：
    1. 并行执行多语言翻译
    2. 并行执行质量评审
    3. 执行一致性评审（按语言对循环组合）
    4. 对未通过的翻译进行重试
    """

    agent_type = "lead"

    def __init__(
        self,
        glossary: Glossary | None = None,
        translation_model: str | None = None,
        review_model: str | None = None,
        quality_threshold: int = QUALITY_THRESHOLD,
        max_retries: int = MAX_RETRIES,
        progress_callback: ProgressCallback | None = None,
        **kwargs,
    ):
        """
        初始化 Lead Agent

        Args:
            glossary: 术语表
            translation_model: 翻译模型
            review_model: 评审模型
            quality_threshold: 质量阈值
            max_retries: 最大重试次数
            progress_callback: 进度回调函数
            **kwargs: 传递给基类的参数
        """
        super().__init__(**kwargs)
        self.glossary = glossary or Glossary()
        self.translation_model = translation_model
        self.review_model = review_model
        self.quality_threshold = quality_threshold
        self.max_retries = max_retries
        self.progress_callback = progress_callback

        # 共享 LLM 客户端
        self._shared_llm_client = UnifiedLLMClient()

    async def cleanup(self) -> None:
        """清理资源"""
        await self._shared_llm_client.close()
        await super().cleanup()

    async def _update_progress(
        self,
        phase: str,
        current_lang: str | None = None,
        completed: int = 0,
        consistency_pair: str | None = None,
        completed_pairs: int = 0,
    ) -> None:
        """更新进度"""
        if self.progress_callback:
            try:
                await self.progress_callback(
                    phase, current_lang, completed, consistency_pair, completed_pairs
                )
            except Exception as e:
                logger.warning(f"[LeadAgent._update_progress] 回调失败: {e}")

    async def _translate_language(
        self,
        source_text: str,
        target_lang: str,
        feedback: ReviewFeedback | None = None,
        key: str | None = None,
        source_text_2: str | None = None,
    ) -> TranslationItem:
        """执行单个语言的翻译"""
        agent = TranslationAgent(
            target_lang=target_lang,
            glossary=self.glossary,
            model=self.translation_model,
            llm_client=self._shared_llm_client,
        )
        return await agent.run(source_text, feedback, key, source_text_2=source_text_2)

    async def _translate_parallel(
        self,
        source_text: str,
        target_langs: list[str],
        feedbacks: dict[str, ReviewFeedback] | None = None,
        key: str | None = None,
        source_text_2: str | None = None,
    ) -> dict[str, TranslationItem]:
        """并行翻译多个语言"""
        feedbacks = feedbacks or {}

        tasks = [
            self._translate_language(
                source_text, lang, feedbacks.get(lang), key, source_text_2=source_text_2
            )
            for lang in target_langs
        ]

        results = await asyncio.gather(*tasks, return_exceptions=True)

        translations: dict[str, TranslationItem] = {}
        for lang, result in zip(target_langs, results, strict=True):
            if isinstance(result, Exception):
                logger.error(
                    f"[LeadAgent._translate_parallel] 翻译失败 [{lang}]: {result}"
                )
                translations[lang] = TranslationItem(
                    target_lang=lang,
                    translated_text=f"[ERROR: {result}]",
                    latency_ms=0,
                )
            else:
                translations[lang] = result

        return translations

    async def _review_quality(
        self,
        source_text: str,
        translations: dict[str, TranslationItem],
        source_text_2: str | None = None,
    ) -> dict[str, tuple[bool, str, list[str]]]:
        """
        并行执行质量评审

        Returns:
            dict[lang, (passed, feedback, suggestions)]
        """
        # 获取人工维护术语（最高优先级）
        curated_terms = (
            self.glossary.find_terms_in_text(source_text) if source_text else []
        )

        async def review_one(lang: str, item: TranslationItem):
            binance_terms = self._collect_binance_review_terms(source_text, lang)
            agent = QualityReviewAgent(
                quality_threshold=self.quality_threshold,
                glossary_terms=binance_terms,
                curated_glossary_terms=curated_terms,
                model=self.review_model,
                llm_client=self._shared_llm_client,
            )
            item.review_input = agent.build_review_input_text(
                source_text=source_text,
                translated_text=item.translated_text,
                target_lang=lang,
                source_text_2=source_text_2,
                glossary_terms_found=item.glossary_terms_found,
                glossary_terms_matched=item.glossary_terms_matched,
                glossary_l1_direct_matches=item.glossary_l1_direct_matches,
            )
            result = await agent.run(
                source_text=source_text,
                translated_text=item.translated_text,
                target_lang=lang,
                source_text_2=source_text_2,
                glossary_terms_found=item.glossary_terms_found,
                glossary_terms_matched=item.glossary_terms_matched,
                glossary_l1_direct_matches=item.glossary_l1_direct_matches,
            )
            return lang, result

        tasks = [review_one(lang, item) for lang, item in translations.items()]

        results = await asyncio.gather(*tasks, return_exceptions=True)

        review_results: dict[str, tuple[bool, str, list[str]]] = {}
        for result in results:
            if isinstance(result, Exception):
                logger.error(f"[LeadAgent._review_quality] 评审失败: {result}")
                continue
            lang, review = result
            review_results[lang] = (
                review.passed,
                review.feedback,
                review.suggestions,
            )
            # 更新翻译项的质量信息
            translations[lang].quality_score = review.score.score
            translations[lang].quality_feedback = review.feedback

        return review_results

    @staticmethod
    def _collect_binance_review_terms(
        source_text: str,
        target_lang: str,
    ) -> list[GlossaryTerm]:
        """
        收集质量评审需要的 Binance 匹配术语（按语言）。

        包含：
        - L1 直接匹配术语（来自 source_text）
        - L2 提示词术语（短术语补充）
        """
        if not source_text:
            return []

        try:
            from app.services.binance_glossary_service import binance_glossary_service

            collected: list[GlossaryTerm] = []
            seen_terms: set[str] = set()

            direct_matches = binance_glossary_service.get_direct_matches(
                source_text, target_lang
            )
            for term_en, translation in direct_matches.items():
                key = term_en.lower()
                if key in seen_terms:
                    continue
                seen_terms.add(key)
                collected.append(
                    GlossaryTerm(
                        term_en=term_en,
                        translations={target_lang: translation},
                        source="binance.com",
                    )
                )

            prompt_terms = binance_glossary_service.get_prompt_terms(
                source_text=source_text,
                target_lang=target_lang,
                exclude_terms=[term.term_en for term in collected],
                max_terms=20,
            )
            for term in prompt_terms:
                key = term.term_en.lower()
                if key in seen_terms:
                    continue
                seen_terms.add(key)
                collected.append(term)

            return collected
        except Exception as e:
            logger.debug(
                f"[LeadAgent._collect_binance_review_terms] Binance terms skip: {e}"
            )
            return []

    async def _review_consistency_pair(
        self,
        source_text: str,
        trans1: TranslationItem,
        trans2: TranslationItem,
        source_text_2: str | None = None,
    ) -> ConsistencyPairResult:
        """
        对单个语言对执行一致性评审

        Args:
            source_text: 源文本
            trans1: 第一种语言的翻译
            trans2: 第二种语言的翻译

        Returns:
            ConsistencyPairResult 语言对一致性评审结果
        """
        # 合并人工维护 glossary 和 Binance L2 glossary
        merged_glossary = self.glossary
        try:
            from app.services.binance_glossary_service import binance_glossary_service

            binance_l2 = binance_glossary_service.get_l2_glossary()
            if binance_l2 and binance_l2.terms:
                merged_glossary = Glossary(
                    terms=list(self.glossary.terms) + list(binance_l2.terms)
                )
                merged_glossary.build_lookup()
        except Exception as e:
            logger.debug(
                f"[LeadAgent._review_consistency_pair] Binance merge skip: {e}"
            )

        agent = ConsistencyReviewAgent(
            glossary=merged_glossary,
            model=self.review_model,
            llm_client=self._shared_llm_client,
        )

        try:
            result = await agent.run(
                source_text, [trans1, trans2], source_text_2=source_text_2
            )
            return ConsistencyPairResult(
                lang1=trans1.target_lang,
                lang2=trans2.target_lang,
                passed=result.passed,
                feedback=result.feedback,
                checked_terms_count=result.checked_terms_count,
                inconsistent_terms_count=result.inconsistent_terms_count,
            )
        except Exception as e:
            logger.error(
                f"[LeadAgent._review_consistency_pair] 一致性评审失败 "
                f"[{trans1.target_lang}<->{trans2.target_lang}]: {e}"
            )
            return ConsistencyPairResult(
                lang1=trans1.target_lang,
                lang2=trans2.target_lang,
                passed=True,
                feedback=f"一致性评审失败: {e}",
            )

    async def _review_consistency_all_pairs(
        self,
        source_text: str,
        translations: dict[str, TranslationItem],
        source_text_2: str | None = None,
    ) -> list[ConsistencyPairResult]:
        """
        对所有语言对执行一致性评审（循环组合）

        使用循环组合方式: (1,2), (2,3), ..., (n-1,n), (n,1)
        组合数量为 n，避免语言多时组合数量过多的问题

        Args:
            source_text: 源文本
            translations: 翻译结果字典 {lang: TranslationItem}

        Returns:
            所有语言对的一致性评审结果列表
        """
        langs = list(translations.keys())
        if len(langs) <= 1:
            return []

        # 生成循环组合: (1,2), (2,3), ..., (n-1,n), (n,1)
        # 组合数量为 n，而非 C(n,2) = n*(n-1)/2
        lang_pairs = [
            (langs[i], langs[(i + 1) % len(langs)]) for i in range(len(langs))
        ]

        logger.info(
            f"[LeadAgent._review_consistency_all_pairs] "
            f"开始一致性评审, {len(lang_pairs)} 个语言对"
        )

        results = []
        for idx, (lang1, lang2) in enumerate(lang_pairs):
            trans1 = translations[lang1]
            trans2 = translations[lang2]

            # 跳过翻译失败的
            if trans1.translated_text.startswith(
                "[ERROR"
            ) or trans2.translated_text.startswith("[ERROR"):
                results.append(
                    ConsistencyPairResult(
                        lang1=lang1,
                        lang2=lang2,
                        passed=True,
                        feedback="跳过：存在翻译失败的语言",
                    )
                )
                continue

            # 更新进度
            pair_name = f"{get_language_name(lang1, chinese=True)}<->{get_language_name(lang2, chinese=True)}"
            await self._update_progress(
                "consistency_review",
                None,
                len(translations),
                pair_name,
                idx,
            )

            result = await self._review_consistency_pair(
                source_text, trans1, trans2, source_text_2=source_text_2
            )
            results.append(result)

            logger.info(
                f"[LeadAgent._review_consistency_all_pairs] "
                f"[{lang1}<->{lang2}] passed={result.passed}"
            )

        return results

    async def run(self, request: TranslationRequest) -> TranslationResponse:
        """
        执行完整的翻译流程

        Args:
            request: 翻译请求

        Returns:
            TranslationResponse 包含所有翻译结果
        """
        start_time = time.perf_counter()

        source_text = request.source_text_1  # 英文源文本（可能为空）
        source_text_2 = request.source_text_2  # 中文源文本（可能为 None）
        target_langs = request.target_langs
        key = request.key

        logger.info(
            f"[LeadAgent.run] 开始翻译流程, "
            f"source_text_1_len={len(source_text)}, "
            f"source_text_2_len={len(source_text_2) if source_text_2 else 0}, "
            f"langs={target_langs}, key={key}"
        )

        # ===== Phase 1: 初始翻译 =====
        await self._update_progress("translating", None, 0)

        translations = await self._translate_parallel(
            source_text, target_langs, key=key, source_text_2=source_text_2
        )

        success_count = len(
            [
                t
                for t in translations.values()
                if not t.translated_text.startswith("[ERROR")
            ]
        )
        logger.info(f"[LeadAgent.run] 初始翻译完成, success={success_count}")

        # ===== Phase 2: 质量评审 =====
        await self._update_progress("quality_review", None, len(translations))

        quality_results = await self._review_quality(
            source_text, translations, source_text_2=source_text_2
        )

        # 找出未通过的翻译
        failed_langs = [
            lang for lang, (passed, _, _) in quality_results.items() if not passed
        ]

        logger.info(
            f"[LeadAgent.run] 质量评审完成, "
            f"passed={len(quality_results) - len(failed_langs)}, "
            f"failed={failed_langs}"
        )

        # ===== Phase 3: 重试未通过的翻译 =====
        retry_count = 0
        # 累积每种语言的重试历史: lang -> [{translation, feedback}]
        feedback_history: dict[str, list[dict[str, str]]] = {}

        while failed_langs and retry_count < self.max_retries:
            retry_count += 1
            completed = len(translations) - len(failed_langs)
            await self._update_progress("retrying", failed_langs[0], completed)

            logger.info(
                f"[LeadAgent.run] 开始重试 (第 {retry_count} 次), "
                f"langs={failed_langs}"
            )

            # 将当前失败状态记入历史（在重翻之前）
            for lang in failed_langs:
                _, fb_text, _ = quality_results.get(lang, (False, "", []))
                feedback_history.setdefault(lang, []).append(
                    {
                        "translation": translations[lang].translated_text,
                        "feedback": fb_text,
                    }
                )

            # 构建反馈（携带完整历史上下文）
            feedbacks = {}
            for lang in failed_langs:
                _, feedback, suggestions = quality_results.get(lang, (False, "", []))
                lang_history = feedback_history.get(lang, [])
                feedbacks[lang] = ReviewFeedback(
                    target_lang=lang,
                    original_translation=translations[lang].translated_text,
                    quality_feedback=feedback,
                    suggestions=suggestions,
                    # 排除最后一条（即当前轮次，已在 original_translation 中）
                    history=lang_history[:-1],
                )

            # 重新翻译
            retried = await self._translate_parallel(
                source_text, failed_langs, feedbacks, key, source_text_2=source_text_2
            )

            for lang, item in retried.items():
                item.retry_count = retry_count
                translations[lang] = item

            # 重新评审
            retry_quality = await self._review_quality(
                source_text,
                {lang: translations[lang] for lang in failed_langs},
                source_text_2=source_text_2,
            )
            quality_results.update(retry_quality)

            # 更新失败列表
            failed_langs = [
                lang for lang, (passed, _, _) in retry_quality.items() if not passed
            ]

        # ===== Phase 4: 一致性评审（按语言对循环组合）=====
        await self._update_progress("consistency_review", None, len(translations))

        consistency_pair_results = await self._review_consistency_all_pairs(
            source_text, translations, source_text_2=source_text_2
        )

        # 计算总体一致性结果
        consistency_passed = all(r.passed for r in consistency_pair_results)
        consistency_feedback = None
        if not consistency_passed:
            failed_pairs = [
                f"{r.lang1}<->{r.lang2}: {r.feedback}"
                for r in consistency_pair_results
                if not r.passed
            ]
            consistency_feedback = "; ".join(failed_pairs)

        logger.info(
            f"[LeadAgent.run] 一致性评审完成, "
            f"passed={consistency_passed}, "
            f"pairs={len(consistency_pair_results)}"
        )

        # ===== 构建响应 =====
        total_latency = (time.perf_counter() - start_time) * 1000
        translation_list = list(translations.values())

        response = TranslationResponse(
            source_text_1=source_text,
            source_lang_1=request.source_lang_1,
            source_text_2=source_text_2,
            source_lang_2=request.source_lang_2,
            source_text=source_text,
            source_lang=request.source_lang,
            translations=translation_list,
            consistency_passed=consistency_passed,
            consistency_feedback=consistency_feedback,
            consistency_pair_results=consistency_pair_results,
            total_latency_ms=total_latency,
        )

        await self._update_progress(
            "completed", None, len(translations), None, len(consistency_pair_results)
        )

        logger.info(
            f"[LeadAgent.run] 翻译流程完成, "
            f"total_latency_ms={total_latency:.2f}, "
            f"translations={len(translation_list)}"
        )

        return response
