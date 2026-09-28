"""
Task Service

异步任务处理服务：FSM 状态机 + AI 处理 + 后台执行。
将 Go ai-api 的 domain service / FSM / handlers 合并为一个 Python 类。
"""

import asyncio
import json
import re
import uuid
from collections import Counter
from datetime import datetime, timezone
from typing import Any

from app.clients.llm_client import UnifiedLLMClient
from app.core.constants import (
    TASK_DEFAULT_MODEL,
    TASK_LANGUAGE_NAMES_ZH,
    TASK_SUPPORTED_LANGUAGES,
)
from app.core.exceptions import (
    InvalidTaskParamsError,
    TaskContentBlockedError,
    TaskNotFoundError,
)
from app.logger import logger
from app.repositories.task_repository import task_repository
from app.schemas.task import (
    BatchGetTaskResponse,
    CreateTaskRequest,
    CreateTaskResponse,
    GetTaskResponse,
    SummarizationOutput,
    TaskStatus,
    TaskType,
    TranslationOutput,
)

# 重试配置
_MAX_RETRIES = 2
_RETRY_DELAY_SECONDS = 20

# Growth 组富文本分隔符标签: <!1>, </!1>, <!2>, </!2>, ...
_GROWTH_TAG_RE = re.compile(r"</?!\d+>")


class TaskService:
    def __init__(self) -> None:
        self._llm_client = UnifiedLLMClient()
        self._running_tasks: dict[str, asyncio.Task[None]] = {}

    # ================================================================
    # 公共 API 方法
    # ================================================================

    async def create_task(self, req: CreateTaskRequest) -> CreateTaskResponse:
        """创建异步任务"""
        task_type = req.task_type
        if task_type not in (TaskType.TRANSLATION, TaskType.SUMMARIZATION):
            raise InvalidTaskParamsError("invalid task_type")

        # 验证并序列化参数
        if task_type == TaskType.TRANSLATION:
            if req.translation_params is None:
                raise InvalidTaskParamsError(
                    "translation_params is required for translation task"
                )
            params = req.translation_params
            if not params.target_languages:
                raise InvalidTaskParamsError("target_languages is required")
            self._validate_languages(params.source_language, params.target_languages)
            params_json = json.dumps(params.model_dump(), ensure_ascii=False)
        else:
            if req.summarization_params is None:
                raise InvalidTaskParamsError(
                    "summarization_params is required for summarization task"
                )
            params_json = json.dumps(
                req.summarization_params.model_dump(), ensure_ascii=False
            )

        task_id = str(uuid.uuid4())
        now = datetime.now(timezone.utc)

        model = req.model or "gemini-2.5-flash"
        user_group = req.user_group or ""

        await task_repository.create(
            task_id=task_id,
            task_type=task_type,
            status=TaskStatus.INIT,
            model=model,
            user_group=user_group,
            params_json=params_json,
        )

        # 后台异步处理
        bg_task = asyncio.create_task(self._process_task_safe(task_id))
        self._running_tasks[task_id] = bg_task
        bg_task.add_done_callback(lambda _: self._running_tasks.pop(task_id, None))

        return CreateTaskResponse(
            task_id=task_id,
            status=TaskStatus.INIT,
            created_at=now.strftime("%Y-%m-%dT%H:%M:%SZ"),
        )

    async def get_task(self, task_id: str) -> GetTaskResponse:
        """获取单个任务"""
        row = await task_repository.get_by_task_id(task_id)
        if row is None:
            raise TaskNotFoundError(task_id)
        return self._row_to_response(row)

    async def batch_get_tasks(self, task_ids: list[str]) -> BatchGetTaskResponse:
        """批量获取任务"""
        if not task_ids:
            return BatchGetTaskResponse(tasks=[])

        rows = await task_repository.get_by_task_ids(task_ids)
        row_map = {r["task_id"]: r for r in rows}

        # 按请求顺序返回，跳过不存在的
        tasks = []
        for tid in task_ids:
            if tid in row_map:
                resp = self._row_to_response(row_map[tid])
                tasks.append(resp.to_dict())
        return BatchGetTaskResponse(tasks=tasks)

    # ================================================================
    # 启动恢复
    # ================================================================

    async def initialize(self) -> None:
        """启动时恢复未完成的任务"""
        from app.db.connection import DatabasePool

        if not DatabasePool.is_initialized():
            logger.warning("[TaskService.initialize] DB 未初始化，跳过任务恢复")
            return

        logger.info("[TaskService.initialize] 加载未完成任务...")
        batch_size = 100
        offset = 0
        total = 0

        while True:
            rows = await task_repository.list_pending(limit=batch_size, offset=offset)
            if not rows:
                break

            for row in rows:
                tid = row["task_id"]
                logger.info(
                    f"[TaskService.initialize] 恢复任务 {tid} "
                    f"(type={row['task_type']}, status={row['status']})"
                )
                bg_task = asyncio.create_task(self._process_task_safe(tid))
                self._running_tasks[tid] = bg_task
                bg_task.add_done_callback(
                    lambda _, t=tid: self._running_tasks.pop(t, None)
                )

            total += len(rows)
            offset += len(rows)
            if len(rows) < batch_size:
                break

        if total:
            logger.info(f"[TaskService.initialize] 已恢复 {total} 个任务")
        else:
            logger.info("[TaskService.initialize] 无未完成任务")

    # ================================================================
    # FSM 处理
    # ================================================================

    async def _process_task_safe(self, task_id: str) -> None:
        """安全包装，防止异常丢失"""
        try:
            await self._process_task(task_id)
        except Exception:
            logger.exception(f"[TaskService] 任务 {task_id} 处理异常")
            try:
                await task_repository.set_error(task_id, "internal processing error")
            except Exception:
                logger.exception(f"[TaskService] 设置任务 {task_id} 错误状态失败")

    async def _process_task(self, task_id: str) -> None:
        """FSM 主循环"""
        while True:
            row = await task_repository.get_by_task_id(task_id)
            if row is None:
                logger.error(f"[_process_task] 任务 {task_id} 不存在")
                break

            status = row["status"]
            if status in (TaskStatus.FINISH, TaskStatus.ERROR):
                break

            await self._handle_state(row)

        logger.info(f"[_process_task] 任务 {task_id} 处理完成")

    async def _handle_state(self, row: dict[str, Any]) -> None:
        """根据当前状态分发处理"""
        status = row["status"]
        task_id = row["task_id"]

        if status in (TaskStatus.INIT, TaskStatus.BEFORE_PROCESS):
            await self._before_process(row)
        elif status == TaskStatus.PROCESSING:
            await self._processing_with_retry(row)
        elif status == TaskStatus.AFTER_PROCESS:
            await self._after_process(row)
        else:
            logger.error(f"[_handle_state] 未知状态 {status} for task {task_id}")

    async def _before_process(self, row: dict[str, Any]) -> None:
        """前置处理：验证参数，推进到 PROCESSING"""
        task_id = row["task_id"]
        task_type = row["task_type"]

        if task_type not in (TaskType.TRANSLATION, TaskType.SUMMARIZATION):
            logger.error(f"[_before_process] 未知任务类型 {task_type} for {task_id}")
            await task_repository.set_error(task_id, f"unknown task_type: {task_type}")
            return

        params = row.get("params")
        if not params:
            logger.error(f"[_before_process] 任务 {task_id} 缺少 params")
            await task_repository.set_error(task_id, "missing params")
            return

        await task_repository.update_status(task_id, TaskStatus.PROCESSING)
        logger.info(f"[_before_process] 任务 {task_id} → PROCESSING")

    async def _processing_with_retry(self, row: dict[str, Any]) -> None:
        """带重试的 AI 处理"""
        task_id = row["task_id"]
        task_type = row["task_type"]

        # 解析 params
        params_raw = row.get("params")
        if isinstance(params_raw, str):
            params = json.loads(params_raw)
        elif isinstance(params_raw, dict):
            params = params_raw
        else:
            await task_repository.set_error(task_id, "invalid params format")
            return

        model = row.get("model") or TASK_DEFAULT_MODEL
        # 确定实际使用的处理模型
        processing_model = self._resolve_processing_model(model)

        last_err: Exception | None = None
        for attempt in range(_MAX_RETRIES):
            try:
                user_group = row.get("user_group", "")
                if task_type == TaskType.TRANSLATION:
                    output = await self._process_translation(
                        params, processing_model, user_group=user_group
                    )
                elif task_type == TaskType.SUMMARIZATION:
                    output = await self._process_summarization(params, processing_model)
                else:
                    await task_repository.set_error(
                        task_id, f"unknown task_type: {task_type}"
                    )
                    return

                # 保存输出
                output_json = json.dumps(output, ensure_ascii=False)
                await task_repository.set_output(task_id, output_json)
                await task_repository.update_status(task_id, TaskStatus.AFTER_PROCESS)
                logger.info(f"[_processing] 任务 {task_id} → AFTER_PROCESS")
                return

            except (InvalidTaskParamsError, TaskContentBlockedError) as e:
                # 不可重试错误
                logger.error(f"[_processing] 不可重试错误 for {task_id}: {e}")
                await task_repository.set_error(task_id, str(e))
                return

            except Exception as e:
                last_err = e
                logger.warning(
                    f"[_processing] 任务 {task_id} 第 {attempt + 1} 次失败: {e}"
                )
                if attempt < _MAX_RETRIES - 1:
                    await asyncio.sleep(_RETRY_DELAY_SECONDS)

        # 所有重试失败
        err_msg = str(last_err) if last_err else "unknown error"
        logger.error(
            f"[_processing] 任务 {task_id} 重试 {_MAX_RETRIES} 次后失败: {err_msg}"
        )
        await task_repository.set_error(task_id, f"AI processing failed: {err_msg}")

    async def _after_process(self, row: dict[str, Any]) -> None:
        """后置处理：当前无额外操作，直接 FINISH"""
        task_id = row["task_id"]
        await task_repository.update_status(task_id, TaskStatus.FINISH)
        logger.info(f"[_after_process] 任务 {task_id} → FINISH")

    # ================================================================
    # AI 处理
    # ================================================================

    async def _process_translation(
        self, params: dict[str, Any], model: str, user_group: str = ""
    ) -> dict[str, Any]:
        """翻译处理：构建 prompt → 调用 LLM → 解析结果"""
        source_language = params.get("source_language", "")
        target_languages = params.get("target_languages", [])
        content = params.get("content", "")

        if not target_languages or not content:
            raise InvalidTaskParamsError("target_languages and content are required")

        # 源语言与目标语言相同时，直接跳过翻译，原样返回
        same_lang_translations: dict[str, str] = {}
        if source_language:
            actual_targets = []
            for lang in target_languages:
                if lang == source_language:
                    same_lang_translations[lang] = content
                else:
                    actual_targets.append(lang)
            target_languages = actual_targets

        # 若全部目标语言 == 源语言，无需调用 LLM
        if not target_languages:
            return {"translations": same_lang_translations}

        # Growth 组：检测富文本分隔符标签
        has_growth_tags = (
            user_group == "growth" and _GROWTH_TAG_RE.search(content) is not None
        )

        # 每种语言独立并发调用 LLM，避免输出过长导致截断/标签丢失
        tasks = [
            self._call_translate_llm(
                content, source_language, [lang], model,
                has_growth_tags=has_growth_tags,
            )
            for lang in target_languages
        ]
        results = await asyncio.gather(*tasks)
        translations: dict[str, str] = {}
        for r in results:
            translations.update(r)

        # 合并同源语言的原样结果
        translations.update(same_lang_translations)
        return {"translations": translations}

    async def _call_translate_llm(
        self,
        content: str,
        source_language: str,
        target_languages: list[str],
        model: str,
        *,
        has_growth_tags: bool = False,
    ) -> dict[str, str]:
        """调用 LLM 执行翻译并返回 {lang_code: translated_text}。"""
        # 构建 prompt
        source_desc = "auto-detected"
        if source_language:
            source_desc = TASK_LANGUAGE_NAMES_ZH.get(source_language, source_language)

        target_descs = [
            TASK_LANGUAGE_NAMES_ZH.get(lang, lang) for lang in target_languages
        ]

        # 构建 JSON 字段说明
        field_hints = []
        for lang in target_languages:
            field_name = self._lang_to_field_name(lang)
            lang_name = TASK_LANGUAGE_NAMES_ZH.get(lang, lang)
            field_hints.append(f'  "{field_name}": "Translation in {lang_name}"')
        json_format = "{\n" + ",\n".join(field_hints) + "\n}"

        growth_tag_instruction = ""
        if has_growth_tags:
            growth_tags = sorted(set(_GROWTH_TAG_RE.findall(content)))
            growth_tag_instruction = (
                f"6. CRITICAL: The source text contains rich-text separator tags: "
                f"{', '.join(growth_tags)}. "
                f"These tags MUST be preserved EXACTLY as-is in the translation. "
                f"Do NOT translate, modify, remove, or reorder these tags. "
                f"Translate only the text between and around the tags.\n"
            )

        prompt = (
            f"You are a professional translator. Translate the following text "
            f"from {source_desc} to the target languages: {', '.join(target_descs)}.\n\n"
            f"Requirements:\n"
            f"1. Preserve the original meaning and tone\n"
            f"2. Use natural and fluent expressions in each target language\n"
            f"3. Keep any technical terms, proper nouns, or formatting\n"
            f"4. Do not add any explanations or notes\n"
            f"5. Return ONLY a JSON object in this exact format:\n{json_format}\n"
            f"{growth_tag_instruction}\n"
            f"Text to translate:\n{content}"
        )

        messages = [{"role": "user", "content": prompt}]
        resp_text = await self._llm_client.chat_completion(
            model=model,
            messages=messages,
            temperature=0.0,
            max_tokens=65536,
        )

        # 解析 JSON
        cleaned = self._clean_json_response(resp_text)
        try:
            result = json.loads(cleaned)
        except json.JSONDecodeError as e:
            logger.error(f"[_call_translate_llm] JSON 解析失败: {e}, text: {cleaned}")
            raise

        # 映射字段名回语言代码
        translations: dict[str, str] = {}
        for lang in target_languages:
            field_name = self._lang_to_field_name(lang)
            if field_name in result:
                translations[lang] = result[field_name]

        # Growth 标签校验
        if has_growth_tags:
            for lang, translated in translations.items():
                tag_issues = self._validate_growth_tags(content, translated)
                if tag_issues:
                    logger.warning(
                        f"[_call_translate_llm] Growth 标签校验失败 "
                        f"lang={lang}: {tag_issues}"
                    )
                    raise ValueError(
                        f"Growth tag preservation failed for {lang}: "
                        f"{', '.join(tag_issues)}"
                    )

        return translations

    async def _process_summarization(
        self, params: dict[str, Any], model: str
    ) -> dict[str, Any]:
        """摘要处理：构建 prompt → 调用 LLM → 解析结果"""
        content = params.get("content", "")
        if not content:
            raise InvalidTaskParamsError("content is required")

        style = params.get("style", "") or "concise"
        max_length = params.get("max_length", 0) or 200
        target_language = params.get("target_language", "")

        target_lang_name = "English"
        if target_language:
            target_lang_name = TASK_LANGUAGE_NAMES_ZH.get(
                target_language, target_language
            )

        style_instructions = {
            "concise": "Provide a brief, concise summary focusing on key points.",
            "detailed": "Provide a comprehensive summary covering all important aspects.",
            "bullet_points": "Provide a summary in bullet point format, listing key points.",
        }.get(style, "Provide a clear and informative summary.")

        prompt = (
            f"You are a professional content summarizer. Summarize the following text.\n\n"
            f"Requirements:\n"
            f"1. Output the summary in {target_lang_name}\n"
            f"2. {style_instructions}\n"
            f"3. Keep the summary under {max_length} characters\n"
            f"4. Maintain the key information and essence of the original text\n"
            f"5. Detect and report the source language\n"
            f'6. Return ONLY a JSON object in this exact format:\n'
            f'{{"summary": "The generated summary", "detected_language": "language-code"}}\n\n'
            f"Text to summarize:\n{content}"
        )

        messages = [{"role": "user", "content": prompt}]
        resp_text = await self._llm_client.chat_completion(
            model=model,
            messages=messages,
            temperature=0.0,
            max_tokens=8192,
        )

        cleaned = self._clean_json_response(resp_text)
        try:
            result = json.loads(cleaned)
        except json.JSONDecodeError as e:
            logger.error(
                f"[_process_summarization] JSON 解析失败: {e}, text: {cleaned}"
            )
            raise

        return {
            "summary": result.get("summary", ""),
            "source_language": result.get("detected_language", ""),
        }

    # ================================================================
    # 工具方法
    # ================================================================

    def _row_to_response(self, row: dict[str, Any]) -> GetTaskResponse:
        """数据库行 → GetTaskResponse"""
        task_type = row["task_type"]
        status = row["status"]

        # 解析输出
        translation_output = None
        summarization_output = None
        if status == TaskStatus.FINISH and row.get("output"):
            output_raw = row["output"]
            if isinstance(output_raw, str):
                output_data = json.loads(output_raw)
            elif isinstance(output_raw, dict):
                output_data = output_raw
            else:
                output_data = None

            if output_data:
                if task_type == TaskType.TRANSLATION:
                    translation_output = TranslationOutput(
                        translations=output_data.get("translations", {})
                    )
                elif task_type == TaskType.SUMMARIZATION:
                    summarization_output = SummarizationOutput(
                        summary=output_data.get("summary", ""),
                        source_language=output_data.get("source_language", ""),
                    )

        return GetTaskResponse(
            task_id=row["task_id"],
            task_type=task_type,
            status=status,
            model=row.get("model", ""),
            user_group=row.get("user_group", "") or "",
            error_message=row.get("error_message", "") or "",
            translation_output=translation_output,
            summarization_output=summarization_output,
            created_at=self._format_datetime(row.get("created_at")),
            updated_at=self._format_datetime(row.get("updated_at")),
            finished_at=self._format_datetime(row.get("finished_at")),
        )

    def _validate_languages(
        self, source: str, targets: list[str]
    ) -> None:
        """验证语言代码"""
        if source and source not in TASK_SUPPORTED_LANGUAGES:
            raise InvalidTaskParamsError(f"unsupported source_language: {source}")
        for lang in targets:
            if lang not in TASK_SUPPORTED_LANGUAGES:
                raise InvalidTaskParamsError(f"unsupported target_language: {lang}")

    def _resolve_processing_model(self, model: str) -> str:
        """解析实际使用的处理模型"""
        from app.core.constants import MODEL_CONFIGS

        if model in MODEL_CONFIGS:
            return model
        # 回退到默认模型
        return TASK_DEFAULT_MODEL

    @staticmethod
    def _validate_growth_tags(source: str, translated: str) -> list[str]:
        """校验 Growth 组富文本标签在翻译结果中是否完整保留。"""
        source_tags = _GROWTH_TAG_RE.findall(source)
        if not source_tags:
            return []

        translated_tags = _GROWTH_TAG_RE.findall(translated)
        source_counts = Counter(source_tags)
        translated_counts = Counter(translated_tags)

        issues: list[str] = []
        for tag, count in source_counts.items():
            t_count = translated_counts.get(tag, 0)
            if t_count == 0:
                issues.append(f"Missing tag: {tag}")
            elif t_count != count:
                issues.append(
                    f"Tag count mismatch: {tag} (expected {count}, got {t_count})"
                )

        for tag in translated_counts:
            if tag not in source_counts:
                issues.append(f"Unexpected tag: {tag}")

        return issues

    @staticmethod
    def _lang_to_field_name(lang: str) -> str:
        """语言代码转 JSON 字段名: 'en-US' → 'en_US'"""
        return lang.replace("-", "_")

    @staticmethod
    def _clean_json_response(text: str) -> str:
        """清理 AI 响应中的 markdown 代码块标记和非法控制字符"""
        text = text.strip()
        if text.startswith("```json"):
            text = text[7:]
        elif text.startswith("```JSON"):
            text = text[7:]
        elif text.startswith("```"):
            text = text[3:]
        if text.endswith("```"):
            text = text[:-3]
        text = text.strip()
        # 移除 JSON 字符串值中不允许的控制字符 (U+0000–U+001F)，
        # 但保留已转义的形式（如 \n, \t）
        text = re.sub(r'[\x00-\x08\x0b\x0c\x0e-\x1f]', '', text)
        # 将未转义的字面换行/回车/制表符替换为对应的转义序列
        # 只处理 JSON 字符串值内部（引号之间）的情况
        def _escape_control_in_strings(m: re.Match) -> str:
            s = m.group(0)
            s = s.replace('\t', '\\t')
            s = s.replace('\n', '\\n')
            s = s.replace('\r', '\\r')
            return s
        text = re.sub(r'"(?:[^"\\]|\\.)*"', _escape_control_in_strings, text)
        return text

    @staticmethod
    def _format_datetime(dt: Any) -> str:
        """格式化 datetime 为 RFC3339"""
        if dt is None:
            return ""
        if isinstance(dt, datetime):
            return dt.strftime("%Y-%m-%dT%H:%M:%SZ")
        if isinstance(dt, str):
            return dt
        return ""


# 全局单例
task_service = TaskService()
