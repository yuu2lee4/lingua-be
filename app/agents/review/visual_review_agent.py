"""
视觉评审 Agent

通过浏览器沙盒截图 + 多模态 LLM 分析翻译在真实 UI 中的视觉呈现质量
"""

import json
import re
import time
from typing import Any

from app.logger import logger
from app.agents.base import BaseAgent
from app.clients.sandbox_client import SandboxClient
from app.core.constants import get_language_name
from app.core.exceptions import SandboxError
from app.schemas.visual_review import (
    VisualReviewRequest,
    VisualReviewResponse,
    VisualLanguageReview,
    VisualIssue,
)


class VisualReviewAgent(BaseAgent):
    """
    视觉评审 Agent

    使用浏览器沙盒截图对比参考语言和目标语言的 UI 呈现，
    通过多模态 LLM 检测布局溢出、文本截断、未翻译内容等问题
    """

    agent_type = "visual_review"

    def __init__(
        self,
        sandbox_client: SandboxClient,
        sandbox_base_url: str = "http://localhost:8000",
        visual_quality_threshold: int = 80,
        **kwargs: Any,
    ):
        super().__init__(**kwargs)
        self._sandbox_client = sandbox_client
        self._sandbox_base_url = sandbox_base_url
        self._visual_quality_threshold = visual_quality_threshold
        self._sandbox_id: str | None = None

    async def setup(self) -> None:
        """创建浏览器沙盒实例"""
        try:
            self._sandbox_id = await self._sandbox_client.create_sandbox(
                name="visual-review",
            )
            logger.info(
                f"[VisualReviewAgent.setup] 沙盒已就绪: {self._sandbox_id}"
            )
        except SandboxError as e:
            logger.error(f"[VisualReviewAgent.setup] 沙盒创建失败: {e}")
            self._sandbox_id = None

    async def cleanup(self) -> None:
        """销毁沙盒实例并清理资源"""
        if self._sandbox_id:
            try:
                await self._sandbox_client.delete_sandbox(self._sandbox_id)
            except Exception as e:
                logger.warning(
                    f"[VisualReviewAgent.cleanup] 沙盒清理失败: {e}"
                )
            self._sandbox_id = None
        await super().cleanup()

    async def run(self, request: VisualReviewRequest) -> VisualReviewResponse:
        """
        执行视觉评审

        Args:
            request: 视觉评审请求

        Returns:
            VisualReviewResponse 评审结果
        """
        start_time = time.time()

        # 沙盒不可用时返回降级响应
        if not self._sandbox_id:
            return VisualReviewResponse(
                reviews=[],
                reference_lang=request.reference_lang,
                total_languages=len(request.target_langs),
                passed_count=0,
                failed_count=0,
                total_latency_ms=0.0,
                sandbox_error="沙盒创建失败，无法执行视觉评审",
            )

        logger.info(
            f"[VisualReviewAgent.run] 开始视觉评审, "
            f"目标语言: {request.target_langs}"
        )

        # 1. 截取参考语言截图
        reference_screenshots = await self._capture_language_screenshots(
            request.base_url,
            request.url_path,
            request.reference_lang,
            request.scroll_positions,
        )

        # 2. 逐个目标语言进行评审（串行，共享沙盒）
        reviews: list[VisualLanguageReview] = []
        for lang_code in request.target_langs:
            review = await self._review_language(
                request=request,
                lang_code=lang_code,
                reference_screenshots=reference_screenshots,
            )
            reviews.append(review)

        # 3. 汇总结果
        passed_count = sum(1 for r in reviews if r.passed)
        elapsed_ms = (time.time() - start_time) * 1000

        response = VisualReviewResponse(
            reviews=reviews,
            reference_lang=request.reference_lang,
            total_languages=len(reviews),
            passed_count=passed_count,
            failed_count=len(reviews) - passed_count,
            total_latency_ms=round(elapsed_ms, 2),
        )

        logger.info(
            f"[VisualReviewAgent.run] 视觉评审完成, "
            f"通过: {passed_count}/{len(reviews)}, "
            f"耗时: {elapsed_ms:.0f}ms"
        )

        return response

    async def _capture_language_screenshots(
        self,
        base_url: str,
        url_path: str,
        lang_code: str,
        scroll_positions: int,
    ) -> list[str]:
        """
        截取指定语言页面的截图

        Args:
            base_url: 网站基础 URL
            url_path: 路径
            lang_code: 语言代码
            scroll_positions: 额外滚动截图次数

        Returns:
            base64 截图列表
        """
        url = f"{base_url}/{lang_code}{url_path}"
        screenshots: list[str] = []

        try:
            await self._sandbox_client.navigate_to_url(self._sandbox_id, url)

            # 首屏截图
            screenshot = await self._sandbox_client.take_screenshot(
                self._sandbox_id
            )
            screenshots.append(screenshot)

            # 滚动后截图
            for _ in range(scroll_positions):
                await self._sandbox_client.scroll_page(self._sandbox_id)
                screenshot = await self._sandbox_client.take_screenshot(
                    self._sandbox_id
                )
                screenshots.append(screenshot)

        except SandboxError as e:
            logger.warning(
                f"[VisualReviewAgent._capture_language_screenshots] "
                f"截图失败 [{lang_code}]: {e}"
            )

        return screenshots

    async def _review_language(
        self,
        request: VisualReviewRequest,
        lang_code: str,
        reference_screenshots: list[str],
    ) -> VisualLanguageReview:
        """
        评审单个目标语言

        Args:
            request: 评审请求
            lang_code: 目标语言代码
            reference_screenshots: 参考语言截图列表

        Returns:
            VisualLanguageReview 评审结果
        """
        lang_name = get_language_name(lang_code)

        # 截取目标语言截图
        target_screenshots = await self._capture_language_screenshots(
            request.base_url,
            request.url_path,
            lang_code,
            request.scroll_positions,
        )

        # 截图失败时返回 0 分
        if not target_screenshots:
            return VisualLanguageReview(
                lang_code=lang_code,
                lang_name=lang_name,
                overall_score=0,
                layout_score=0,
                text_rendering_score=0,
                translation_completeness_score=0,
                passed=False,
                issues=[],
                screenshots_count=0,
                feedback=f"截图失败，无法评审 {lang_name}",
            )

        # 构建多模态消息并调用 LLM
        try:
            messages = self._build_review_messages(
                lang_code=lang_code,
                lang_name=lang_name,
                reference_lang=request.reference_lang,
                reference_screenshots=reference_screenshots,
                target_screenshots=target_screenshots,
            )
            response = await self._call_llm(
                messages=messages,
                temperature=0.2,
                max_tokens=4096,
            )
            return self._parse_review_response(
                response=response,
                lang_code=lang_code,
                lang_name=lang_name,
                screenshots_count=len(target_screenshots),
            )
        except Exception as e:
            logger.error(
                f"[VisualReviewAgent._review_language] "
                f"LLM 评审失败 [{lang_code}]: {e}"
            )
            return VisualLanguageReview(
                lang_code=lang_code,
                lang_name=lang_name,
                overall_score=70,
                layout_score=70,
                text_rendering_score=70,
                translation_completeness_score=70,
                expression_accuracy_score=70,
                passed=70 >= self._visual_quality_threshold,
                issues=[],
                screenshots_count=len(target_screenshots),
                feedback=f"LLM 评审失败: {e}",
            )

    def _build_review_messages(
        self,
        lang_code: str,
        lang_name: str,
        reference_lang: str,
        reference_screenshots: list[str],
        target_screenshots: list[str],
    ) -> list[dict[str, Any]]:
        """
        构建多模态评审消息

        将参考语言和目标语言截图以 Anthropic content blocks 格式组装
        """
        reference_lang_name = get_language_name(reference_lang)

        # 构建 content blocks
        content_blocks: list[dict[str, Any]] = []

        # 参考语言截图
        content_blocks.append({
            "type": "text",
            "text": (
                f"Below are screenshots of the {reference_lang_name} "
                f"(reference) version of the page:"
            ),
        })
        for screenshot in reference_screenshots:
            content_blocks.append({
                "type": "image",
                "source": {
                    "type": "base64",
                    "media_type": "image/png",
                    "data": screenshot,
                },
            })

        # 目标语言截图
        content_blocks.append({
            "type": "text",
            "text": (
                f"Below are screenshots of the {lang_name} ({lang_code}) "
                f"translation of the same page:"
            ),
        })
        for screenshot in target_screenshots:
            content_blocks.append({
                "type": "image",
                "source": {
                    "type": "base64",
                    "media_type": "image/png",
                    "data": screenshot,
                },
            })

        # 评审提示词
        content_blocks.append({
            "type": "text",
            "text": self._build_review_prompt(lang_code, lang_name),
        })

        return [
            {
                "role": "system",
                "content": (
                    "You are a professional UI/UX translation quality reviewer "
                    "specializing in cryptocurrency exchange platforms. "
                    "You analyze screenshots to detect visual issues with "
                    "translated content. Always respond with valid JSON."
                ),
            },
            {
                "role": "user",
                "content": content_blocks,
            },
        ]

    def _build_review_prompt(self, lang_code: str, lang_name: str) -> str:
        """构建评审提示词"""
        return f"""Compare the reference (English) screenshots with the \
{lang_name} ({lang_code}) translation screenshots above.

Evaluate the translation's visual quality on these dimensions:

1. **Layout Quality** (layout_score: 0-100):
   - Text overflow beyond containers
   - Text truncation with ellipsis or cut-off
   - Broken layout or misaligned elements
   - Buttons/labels that are too wide or too narrow

2. **Text Rendering** (text_rendering_score: 0-100):
   - Encoding issues (garbled characters, mojibake)
   - Font rendering problems
   - Incorrect character display
   - Missing glyphs or placeholder boxes

3. **Translation Completeness** (translation_completeness_score: 0-100):
   - Untranslated English text remaining
   - Placeholder strings (e.g., {{{{key}}}}) visible
   - Mixed language content that shouldn't be mixed
   - Missing translations leaving blank spaces

For each issue found, classify it as:
- **issue_type**: truncation|overflow|encoding|layout|untranslated|mistranslation|style
- **severity**: critical (breaks usability), major (noticeable problem), minor (cosmetic)

Respond in this exact JSON format:
{{
    "overall_score": <0-100>,
    "layout_score": <0-100>,
    "text_rendering_score": <0-100>,
    "translation_completeness_score": <0-100>,
    "issues": [
        {{
            "issue_type": "<type>",
            "severity": "<severity>",
            "location": "<页面位置，中文，不超过10个字>",
            "description": "<问题描述，中文，不超过10个字>",
            "suggestion": "<修复建议，中文，不超过10个字>"
        }}
    ],
    "feedback": "<中文反馈，仅列出低于95分的维度，不超过10个字；所有维度>=95时留空>"
}}

Important rules for feedback, description, suggestion and location:
- 所有文本字段必须使用中文，每条不超过10个字
- feedback 仅包含低于95分的维度摘要，所有维度>=95分时为空字符串""
- issues 仅报告低于95分的维度相关问题

Return ONLY the JSON object, no additional text."""

    def _parse_review_response(
        self,
        response: str,
        lang_code: str,
        lang_name: str,
        screenshots_count: int,
    ) -> VisualLanguageReview:
        """解析 LLM 评审响应"""
        json_match = re.search(r"\{[\s\S]*\}", response)
        if not json_match:
            logger.warning(
                f"[VisualReviewAgent._parse_review_response] "
                f"无法提取 JSON [{lang_code}]: {response[:200]}"
            )
            return self._default_review(lang_code, lang_name, screenshots_count)

        try:
            parsed = json.loads(json_match.group())
        except json.JSONDecodeError as e:
            logger.warning(
                f"[VisualReviewAgent._parse_review_response] "
                f"JSON 解析失败 [{lang_code}]: {e}"
            )
            return self._default_review(lang_code, lang_name, screenshots_count)

        overall_score = int(parsed.get("overall_score", 70))
        issues = [
            VisualIssue(
                issue_type=issue.get("issue_type", "layout"),
                severity=issue.get("severity", "minor"),
                location=issue.get("location", "unknown"),
                description=issue.get("description", ""),
                suggestion=issue.get("suggestion", ""),
            )
            for issue in parsed.get("issues", [])
        ]

        return VisualLanguageReview(
            lang_code=lang_code,
            lang_name=lang_name,
            overall_score=overall_score,
            layout_score=int(parsed.get("layout_score", 70)),
            text_rendering_score=int(parsed.get("text_rendering_score", 70)),
            translation_completeness_score=int(
                parsed.get("translation_completeness_score", 70)
            ),
            passed=overall_score >= self._visual_quality_threshold,
            issues=issues,
            screenshots_count=screenshots_count,
            feedback=parsed.get("feedback", ""),
        )

    def _default_review(
        self,
        lang_code: str,
        lang_name: str,
        screenshots_count: int,
    ) -> VisualLanguageReview:
        """LLM 解析失败时返回默认评审结果"""
        return VisualLanguageReview(
            lang_code=lang_code,
            lang_name=lang_name,
            overall_score=70,
            layout_score=70,
            text_rendering_score=70,
            translation_completeness_score=70,
            passed=70 >= self._visual_quality_threshold,
            issues=[],
            screenshots_count=screenshots_count,
            feedback="Unable to parse visual review response",
        )
