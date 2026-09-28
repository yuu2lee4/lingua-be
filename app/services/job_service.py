"""
任务服务

管理翻译任务的生命周期
"""

import uuid

from app.core.constants import JobStatus
from app.logger import logger
from app.schemas.job import JobResult, JobStatusResponse, JobSubmitResponse
from app.schemas.translation import TranslationRequest, TranslationResponse
from app.storage.job_store import JobStore, job_store


class JobService:
    """任务服务"""

    def __init__(self, store: JobStore | None = None):
        self._store = store or job_store

    def _generate_job_id(self) -> str:
        """生成任务 ID"""
        return str(uuid.uuid4())

    async def create_job(self, request: TranslationRequest) -> JobSubmitResponse:
        """
        创建新任务

        Args:
            request: 翻译请求

        Returns:
            JobSubmitResponse 包含任务 ID
        """
        job_id = self._generate_job_id()

        await self._store.create(job_id, request)

        logger.info(f"[JobService.create_job] 创建任务: {job_id}")

        return JobSubmitResponse(
            job_id=job_id,
            status=JobStatus.PENDING,
            message="任务已提交",
        )

    async def get_job(self, job_id: str) -> JobResult:
        """
        获取任务详情

        Args:
            job_id: 任务 ID

        Returns:
            JobResult 任务详情
        """
        return await self._store.get(job_id)

    async def get_job_status(self, job_id: str) -> JobStatusResponse:
        """
        获取任务状态

        Args:
            job_id: 任务 ID

        Returns:
            JobStatusResponse 任务状态
        """
        job = await self._store.get(job_id)

        return JobStatusResponse(
            job_id=job.job_id,
            status=job.status,
            progress=job.progress,
            response=job.response,
            error=job.error,
            created_at=job.created_at,
            updated_at=job.updated_at,
            completed_at=job.completed_at,
        )

    async def start_job(self, job_id: str) -> JobResult:
        """
        开始执行任务

        Args:
            job_id: 任务 ID

        Returns:
            JobResult 更新后的任务
        """
        job = await self._store.update_status(job_id, JobStatus.IN_PROGRESS)
        await self._store.update_progress(job_id, current_phase="starting")

        logger.info(f"[JobService.start_job] 开始任务: {job_id}")

        return job

    async def update_progress(
        self,
        job_id: str,
        current_phase: str | None = None,
        current_language: str | None = None,
        completed_languages: int | None = None,
        retry_count: int | None = None,
        total_consistency_pairs: int | None = None,
        current_consistency_pair: str | None = None,
        completed_consistency_pairs: int | None = None,
    ) -> JobResult:
        """
        更新任务进度

        Args:
            job_id: 任务 ID
            current_phase: 当前阶段
            current_language: 当前处理的语言
            completed_languages: 已完成的语言数
            retry_count: 重试次数
            total_consistency_pairs: 一致性评审语言对总数
            current_consistency_pair: 当前评审的语言对
            completed_consistency_pairs: 已完成的一致性评审语言对数

        Returns:
            JobResult 更新后的任务
        """
        return await self._store.update_progress(
            job_id,
            current_phase=current_phase,
            current_language=current_language,
            completed_languages=completed_languages,
            retry_count=retry_count,
            total_consistency_pairs=total_consistency_pairs,
            current_consistency_pair=current_consistency_pair,
            completed_consistency_pairs=completed_consistency_pairs,
        )

    async def complete_job(
        self,
        job_id: str,
        response: TranslationResponse,
    ) -> JobResult:
        """
        完成任务

        Args:
            job_id: 任务 ID
            response: 翻译响应

        Returns:
            JobResult 更新后的任务
        """
        await self._store.set_response(job_id, response)
        job = await self._store.update_status(job_id, JobStatus.COMPLETED)
        await self._store.update_progress(
            job_id,
            current_phase="completed",
            completed_languages=len(response.translations),
        )

        logger.info(f"[JobService.complete_job] 任务完成: {job_id}")

        return job

    async def fail_job(self, job_id: str, error: str) -> JobResult:
        """
        标记任务失败

        Args:
            job_id: 任务 ID
            error: 错误信息

        Returns:
            JobResult 更新后的任务
        """
        job = await self._store.update_status(
            job_id, JobStatus.FAILED, error=error
        )
        await self._store.update_progress(job_id, current_phase="failed")

        logger.error(f"[JobService.fail_job] 任务失败: {job_id}, error={error}")

        return job

    async def cancel_job(self, job_id: str) -> JobResult:
        """
        取消任务

        Args:
            job_id: 任务 ID

        Returns:
            JobResult 更新后的任务
        """
        job = await self._store.get(job_id)

        # 只能取消 PENDING 或 IN_PROGRESS 的任务
        if job.status not in (JobStatus.PENDING, JobStatus.IN_PROGRESS):
            raise ValueError(f"无法取消状态为 {job.status} 的任务")

        job = await self._store.update_status(job_id, JobStatus.CANCELLED)
        await self._store.update_progress(job_id, current_phase="cancelled")

        logger.info(f"[JobService.cancel_job] 任务已取消: {job_id}")

        return job

    async def delete_job(self, job_id: str) -> None:
        """
        删除任务

        Args:
            job_id: 任务 ID
        """
        await self._store.delete(job_id)
        logger.info(f"[JobService.delete_job] 任务已删除: {job_id}")

    async def list_jobs(
        self,
        status: JobStatus | None = None,
        limit: int = 100,
    ) -> list[JobResult]:
        """
        列出任务

        Args:
            status: 状态过滤
            limit: 数量限制

        Returns:
            任务列表
        """
        return await self._store.list_jobs(status=status, limit=limit)


# 全局单例
job_service = JobService()
