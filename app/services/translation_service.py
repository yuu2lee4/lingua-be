"""
翻译服务

协调 LeadAgent 执行翻译任务
"""

import asyncio
from pathlib import Path

from app.agents.lead_agent import LeadAgent
from app.core.constants import MAX_RETRIES, QUALITY_THRESHOLD
from app.logger import logger
from app.schemas.glossary import Glossary
from app.schemas.translation import TranslationRequest, TranslationResponse
from app.services.glossary_service import get_default_glossary, glossary_service
from app.services.job_service import JobService, job_service


class TranslationService:
    """翻译服务"""

    def __init__(
        self,
        job_svc: JobService | None = None,
    ):
        self._job_service = job_svc or job_service
        self._running_tasks: dict[str, asyncio.Task] = {}

    async def submit_translation(
        self, request: TranslationRequest
    ) -> str:
        """
        提交翻译任务

        Args:
            request: 翻译请求

        Returns:
            job_id 任务 ID
        """
        # 创建任务
        submit_response = await self._job_service.create_job(request)
        job_id = submit_response.job_id

        # 启动后台任务
        task = asyncio.create_task(self._execute_translation(job_id, request))
        self._running_tasks[job_id] = task

        # 注册清理回调
        task.add_done_callback(
            lambda t: self._running_tasks.pop(job_id, None)
        )

        logger.info(f"[TranslationService.submit_translation] 任务已提交: {job_id}")

        return job_id

    async def _execute_translation(
        self,
        job_id: str,
        request: TranslationRequest,
    ) -> None:
        """
        执行翻译任务（后台）

        Args:
            job_id: 任务 ID
            request: 翻译请求
        """
        logger.info(f"[TranslationService._execute_translation] 开始执行任务: {job_id}")

        try:
            # 标记任务开始
            await self._job_service.start_job(job_id)

            # 加载术语表
            glossary = await self._load_glossary(request.glossary_path)

            # 创建进度回调
            async def progress_callback(
                phase: str,
                current_lang: str | None,
                completed: int,
                consistency_pair: str | None = None,
                completed_pairs: int = 0,
            ) -> None:
                await self._job_service.update_progress(
                    job_id,
                    current_phase=phase,
                    current_language=current_lang,
                    completed_languages=completed,
                    current_consistency_pair=consistency_pair,
                    completed_consistency_pairs=completed_pairs,
                )

            # 创建并运行 LeadAgent
            async with LeadAgent(
                glossary=glossary,
                translation_model=request.translation_model,
                review_model=request.review_model,
                quality_threshold=request.quality_threshold or QUALITY_THRESHOLD,
                max_retries=request.max_retries or MAX_RETRIES,
                progress_callback=progress_callback,
            ) as agent:
                response = await agent.run(request)

            # 完成任务
            await self._job_service.complete_job(job_id, response)

            logger.info(
                f"[TranslationService._execute_translation] 任务完成: {job_id}"
            )

        except asyncio.CancelledError:
            logger.info(
                f"[TranslationService._execute_translation] 任务被取消: {job_id}"
            )
            raise

        except Exception as e:
            logger.error(
                f"[TranslationService._execute_translation] "
                f"任务失败: {job_id}, error={e}"
            )
            await self._job_service.fail_job(job_id, str(e))

    async def _load_glossary(self, glossary_path: str | None) -> Glossary:
        """
        加载术语表

        Args:
            glossary_path: 术语表路径，为空使用默认

        Returns:
            Glossary 术语表
        """
        if glossary_path:
            path = Path(glossary_path)
            if not path.is_absolute():
                # 相对路径基于 data 目录
                base_dir = Path(__file__).parent.parent.parent
                path = base_dir / "data" / glossary_path

            if path.exists():
                return glossary_service.load_glossary(path)
            else:
                logger.warning(
                    f"[TranslationService._load_glossary] 术语表不存在: {path}"
                )

        # 使用默认术语表
        return get_default_glossary()

    async def cancel_translation(self, job_id: str) -> bool:
        """
        取消翻译任务

        Args:
            job_id: 任务 ID

        Returns:
            是否成功取消
        """
        # 取消后台任务
        task = self._running_tasks.get(job_id)
        if task and not task.done():
            task.cancel()
            try:
                await task
            except asyncio.CancelledError:
                pass

        # 更新任务状态
        await self._job_service.cancel_job(job_id)

        logger.info(f"[TranslationService.cancel_translation] 任务已取消: {job_id}")

        return True

    async def translate_sync(
        self, request: TranslationRequest
    ) -> TranslationResponse:
        """
        同步执行翻译（阻塞等待结果）

        Args:
            request: 翻译请求

        Returns:
            TranslationResponse 翻译响应
        """
        # 加载术语表
        glossary = await self._load_glossary(request.glossary_path)

        # 直接执行
        async with LeadAgent(
            glossary=glossary,
            translation_model=request.translation_model,
            review_model=request.review_model,
            quality_threshold=request.quality_threshold or QUALITY_THRESHOLD,
            max_retries=request.max_retries or MAX_RETRIES,
        ) as agent:
            return await agent.run(request)


# 全局单例
translation_service = TranslationService()
