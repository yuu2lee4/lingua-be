"""
视觉评审 API 端点

通过浏览器沙盒截图 + 多模态 LLM 评审翻译的视觉呈现质量
"""

from fastapi import APIRouter, HTTPException, status

from app.logger import logger
from app.core.exceptions import TranslationServiceError
from app.schemas.visual_review import VisualReviewRequest, VisualReviewResponse
from app.services.visual_review_service import visual_review_service


router = APIRouter(prefix="/visual-reviews", tags=["visual-reviews"])


@router.post(
    "",
    response_model=VisualReviewResponse,
    summary="执行视觉评审",
    description="通过浏览器沙盒截图对比各语言 UI 呈现，检测布局溢出、文本截断等问题",
)
async def execute_visual_review(
    request: VisualReviewRequest,
) -> VisualReviewResponse:
    """
    执行视觉评审

    - **target_langs**: 目标语言代码列表，如 ["ja-JP", "ko-KR"]
    - **base_url**: 网站基础 URL
    - **url_path**: 语言代码后的路径
    - **reference_lang**: 参考语言代码
    - **scroll_positions**: 截图滚动次数
    - **review_model**: 可选，评审模型
    - **sandbox_resolution**: 沙盒分辨率
    """
    try:
        response = await visual_review_service.execute_visual_review(request)

        logger.info(
            f"[execute_visual_review] 视觉评审完成, "
            f"通过: {response.passed_count}/{response.total_languages}"
        )

        return response

    except TranslationServiceError as e:
        logger.error(f"[execute_visual_review] 服务错误: {e}")
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e),
        )

    except Exception as e:
        logger.error(f"[execute_visual_review] 未知错误: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="视觉评审执行失败",
        )
