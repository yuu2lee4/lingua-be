"""
任务存储

内存实现的任务存储，支持 TTL 自动清理
"""

import asyncio
from collections.abc import Callable
from datetime import datetime

from app.core.constants import JOB_TTL_SECONDS, JobStatus
from app.core.exceptions import JobAlreadyExistsError, JobNotFoundError
from app.logger import logger
from app.schemas.job import JobProgress, JobResult
from app.schemas.translation import TranslationRequest, TranslationResponse


class JobStore:
    """
    内存任务存储

    支持 CRUD 操作和 TTL 自动清理
    """

    def __init__(self, ttl_seconds: int = JOB_TTL_SECONDS):
        self._jobs: dict[str, JobResult] = {}
        self._ttl_seconds = ttl_seconds
        self._cleanup_task: asyncio.Task | None = None
        self._callbacks: dict[str, list[Callable]] = {}

    async def start_cleanup_task(self) -> None:
        """启动后台清理任务"""
        if self._cleanup_task is None:
            self._cleanup_task = asyncio.create_task(self._cleanup_loop())
            logger.info("[JobStore] 启动后台清理任务")

    async def stop_cleanup_task(self) -> None:
        """停止后台清理任务"""
        if self._cleanup_task is not None:
            self._cleanup_task.cancel()
            try:
                await self._cleanup_task
            except asyncio.CancelledError:
                pass
            self._cleanup_task = None
            logger.info("[JobStore] 停止后台清理任务")

    async def _cleanup_loop(self) -> None:
        """清理循环"""
        while True:
            try:
                await asyncio.sleep(60)  # 每分钟清理一次
                await self._cleanup_expired()
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"[JobStore] 清理任务出错: {e}")

    async def _cleanup_expired(self) -> None:
        """清理过期任务"""
        now = datetime.now()
        expired_ids = []

        for job_id, job in self._jobs.items():
            # 计算任务年龄
            age = (now - job.created_at).total_seconds()
            if age > self._ttl_seconds:
                expired_ids.append(job_id)

        for job_id in expired_ids:
            del self._jobs[job_id]
            if job_id in self._callbacks:
                del self._callbacks[job_id]

        if expired_ids:
            logger.info(f"[JobStore] 清理了 {len(expired_ids)} 个过期任务")

    async def create(
        self, job_id: str, request: TranslationRequest
    ) -> JobResult:
        """创建新任务"""
        if job_id in self._jobs:
            raise JobAlreadyExistsError(job_id)

        # 计算一致性评审语言对数: C(n, 2) = n * (n - 1) / 2
        n_langs = len(request.target_langs)
        total_consistency_pairs = n_langs * (n_langs - 1) // 2 if n_langs > 1 else 0

        job = JobResult(
            job_id=job_id,
            status=JobStatus.PENDING,
            progress=JobProgress(
                total_languages=n_langs,
                completed_languages=0,
                current_phase="pending",
                total_consistency_pairs=total_consistency_pairs,
                completed_consistency_pairs=0,
            ),
            request=request,
            created_at=datetime.now(),
            updated_at=datetime.now(),
        )

        self._jobs[job_id] = job
        logger.info(f"[JobStore] 创建任务: {job_id}")
        return job

    async def get(self, job_id: str) -> JobResult:
        """获取任务"""
        if job_id not in self._jobs:
            raise JobNotFoundError(job_id)
        return self._jobs[job_id]

    async def exists(self, job_id: str) -> bool:
        """检查任务是否存在"""
        return job_id in self._jobs

    async def update_status(
        self,
        job_id: str,
        status: JobStatus,
        error: str | None = None,
    ) -> JobResult:
        """更新任务状态"""
        job = await self.get(job_id)
        job.status = status
        job.updated_at = datetime.now()

        if error:
            job.error = error

        if status in (JobStatus.COMPLETED, JobStatus.FAILED, JobStatus.CANCELLED):
            job.completed_at = datetime.now()

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
        """更新任务进度"""
        job = await self.get(job_id)
        job.updated_at = datetime.now()

        if current_phase is not None:
            job.progress.current_phase = current_phase

        if current_language is not None:
            job.progress.current_language = current_language

        if completed_languages is not None:
            job.progress.completed_languages = completed_languages

        if retry_count is not None:
            job.progress.retry_count = retry_count

        if total_consistency_pairs is not None:
            job.progress.total_consistency_pairs = total_consistency_pairs

        if current_consistency_pair is not None:
            job.progress.current_consistency_pair = current_consistency_pair

        if completed_consistency_pairs is not None:
            job.progress.completed_consistency_pairs = completed_consistency_pairs

        return job

    async def set_response(
        self, job_id: str, response: TranslationResponse
    ) -> JobResult:
        """设置任务结果"""
        job = await self.get(job_id)
        job.response = response
        job.updated_at = datetime.now()
        return job

    async def delete(self, job_id: str) -> None:
        """删除任务"""
        if job_id not in self._jobs:
            raise JobNotFoundError(job_id)

        del self._jobs[job_id]
        if job_id in self._callbacks:
            del self._callbacks[job_id]

        logger.info(f"[JobStore] 删除任务: {job_id}")

    async def list_jobs(
        self,
        status: JobStatus | None = None,
        limit: int = 100,
    ) -> list[JobResult]:
        """列出任务"""
        jobs = list(self._jobs.values())

        if status is not None:
            jobs = [j for j in jobs if j.status == status]

        # 按创建时间倒序
        jobs.sort(key=lambda j: j.created_at, reverse=True)

        return jobs[:limit]

    def count(self) -> int:
        """获取任务数量"""
        return len(self._jobs)


# 全局单例
job_store = JobStore()
