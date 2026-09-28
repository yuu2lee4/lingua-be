"""
翻译 API 端点

提供异步翻译任务的提交、查询和取消功能
"""

from fastapi import APIRouter, HTTPException, status

from app.logger import logger
from app.core.exceptions import JobNotFoundError, TranslationServiceError
from app.schemas.translation import TranslationRequest, TranslationResponse
from app.schemas.job import JobSubmitResponse, JobStatusResponse
from app.services.job_service import job_service
from app.services.translation_service import translation_service


router = APIRouter(prefix="/translations", tags=["translations"])


@router.post(
    "",
    response_model=JobSubmitResponse,
    status_code=status.HTTP_202_ACCEPTED,
    summary="提交翻译任务",
    description="提交异步翻译任务，返回任务 ID 用于后续查询",
)
async def submit_translation(request: TranslationRequest) -> JobSubmitResponse:
    """
    提交翻译任务

    - **source_text**: 源文本（英文）
    - **target_langs**: 目标语言代码列表，如 ["ja-JP", "ko-KR"]
    - **glossary_path**: 可选，术语表文件路径
    - **translation_model**: 可选，翻译模型
    - **review_model**: 可选，评审模型
    - **quality_threshold**: 可选，质量阈值 (0-100)
    - **max_retries**: 可选，最大重试次数
    """
    try:
        job_id = await translation_service.submit_translation(request)

        logger.info(f"[submit_translation] 任务已提交: {job_id}")

        return JobSubmitResponse(
            job_id=job_id,
            status="pending",
            message="任务已提交，请使用任务 ID 查询状态",
        )

    except TranslationServiceError as e:
        logger.error(f"[submit_translation] 服务错误: {e}")
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e),
        )

    except Exception as e:
        logger.error(f"[submit_translation] 未知错误: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="翻译任务提交失败",
        )


@router.post(
    "/sync",
    response_model=TranslationResponse,
    summary="同步翻译",
    description="同步执行翻译，直接返回结果（无需轮询）",
)
async def translate_sync(request: TranslationRequest) -> TranslationResponse:
    """
    同步翻译（阻塞等待结果）

    - **source_text_1**: 主源文本（英文）
    - **source_text_2**: 可选，辅助源文本（中文）
    - **target_langs**: 目标语言代码列表
    - **quality_threshold**: 可选，质量阈值 (0-100)
    - **max_retries**: 可选，最大重试次数
    """
    try:
        response = await translation_service.translate_sync(request)
        logger.info(
            f"[translate_sync] 翻译完成: "
            f"langs={[t.target_lang for t in response.translations]}"
        )
        return response

    except TranslationServiceError as e:
        logger.error(f"[translate_sync] 服务错误: {e}")
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e),
        )

    except Exception as e:
        logger.error(f"[translate_sync] 翻译失败: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="同步翻译失败",
        )


@router.get(
    "/{job_id}",
    response_model=JobStatusResponse,
    summary="查询任务状态",
    description="根据任务 ID 查询翻译任务的状态和结果",
)
async def get_translation_status(job_id: str) -> JobStatusResponse:
    """
    查询任务状态

    - **job_id**: 任务 ID

    返回任务的当前状态：
    - pending: 等待执行
    - in_progress: 执行中
    - completed: 已完成（包含翻译结果）
    - failed: 失败（包含错误信息）
    - cancelled: 已取消
    """
    try:
        status_response = await job_service.get_job_status(job_id)

        logger.info(
            f"[get_translation_status] 查询任务: {job_id}, "
            f"status={status_response.status}"
        )

        return status_response

    except JobNotFoundError:
        logger.warning(f"[get_translation_status] 任务不存在: {job_id}")
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"任务不存在: {job_id}",
        )

    except Exception as e:
        logger.error(f"[get_translation_status] 查询失败: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="任务查询失败",
        )


@router.delete(
    "/{job_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="取消任务",
    description="取消进行中的翻译任务",
)
async def cancel_translation(job_id: str) -> None:
    """
    取消翻译任务

    - **job_id**: 任务 ID

    只能取消 pending 或 in_progress 状态的任务
    """
    try:
        await translation_service.cancel_translation(job_id)

        logger.info(f"[cancel_translation] 任务已取消: {job_id}")

    except JobNotFoundError:
        logger.warning(f"[cancel_translation] 任务不存在: {job_id}")
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"任务不存在: {job_id}",
        )

    except ValueError as e:
        logger.warning(f"[cancel_translation] 无法取消: {e}")
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e),
        )

    except Exception as e:
        logger.error(f"[cancel_translation] 取消失败: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="任务取消失败",
        )
