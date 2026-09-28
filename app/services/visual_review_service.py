"""
视觉评审服务

协调 VisualReviewAgent 执行视觉评审任务
"""

import os

from app.logger import logger
from app.agents.review.visual_review_agent import VisualReviewAgent
from app.clients.sandbox_client import SandboxClient
from app.schemas.visual_review import VisualReviewRequest, VisualReviewResponse


class VisualReviewService:
    """视觉评审服务"""

    def __init__(
        self,
        sandbox_base_url: str | None = None,
    ):
        self._sandbox_base_url = sandbox_base_url or os.getenv(
            "SANDBOX_API_URL", "http://localhost:8000"
        )

    async def execute_visual_review(
        self, request: VisualReviewRequest
    ) -> VisualReviewResponse:
        """
        执行视觉评审

        创建沙盒客户端和 Agent，通过 async with 管理生命周期。
        沙盒不可用时返回降级响应，不抛异常。

        Args:
            request: 视觉评审请求

        Returns:
            VisualReviewResponse 评审结果
        """
        logger.info(
            f"[VisualReviewService.execute_visual_review] "
            f"开始视觉评审, 目标语言: {request.target_langs}"
        )

        sandbox_client = SandboxClient(
            base_url=self._sandbox_base_url,
        )

        try:
            async with VisualReviewAgent(
                sandbox_client=sandbox_client,
                sandbox_base_url=self._sandbox_base_url,
                model=request.review_model,
            ) as agent:
                response = await agent.run(request)

            logger.info(
                f"[VisualReviewService.execute_visual_review] "
                f"视觉评审完成, "
                f"通过: {response.passed_count}/{response.total_languages}"
            )

            return response

        except Exception as e:
            logger.error(
                f"[VisualReviewService.execute_visual_review] "
                f"视觉评审失败: {e}"
            )
            return VisualReviewResponse(
                reviews=[],
                reference_lang=request.reference_lang,
                total_languages=len(request.target_langs),
                passed_count=0,
                failed_count=0,
                total_latency_ms=0.0,
                sandbox_error=f"视觉评审执行失败: {e}",
            )

        finally:
            await sandbox_client.close()


# 全局单例
visual_review_service = VisualReviewService()
