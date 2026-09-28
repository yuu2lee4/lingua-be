"""
Task API Schemas

异步任务 API 的请求/响应模型，匹配 Go ai-api 的 protobuf JSON 格式。
"""

from enum import IntEnum
from typing import Any

from pydantic import BaseModel, Field


class TaskType(IntEnum):
    """任务类型"""

    UNKNOWN = 0
    TRANSLATION = 1
    SUMMARIZATION = 2


class TaskStatus(IntEnum):
    """任务状态 (FSM)"""

    INIT = 0
    BEFORE_PROCESS = 1
    PROCESSING = 2
    AFTER_PROCESS = 3
    FINISH = 4
    ERROR = 5


# ============ 参数 / 输出 ============


class TranslationParams(BaseModel):
    source_language: str = ""
    target_languages: list[str]
    content: str


class SummarizationParams(BaseModel):
    content: str
    source_language: str = ""
    target_language: str = ""
    max_length: int = 200
    style: str = "concise"


class TranslationOutput(BaseModel):
    translations: dict[str, str]


class SummarizationOutput(BaseModel):
    summary: str
    source_language: str = ""


# ============ 请求 ============


class CreateTaskRequest(BaseModel):
    task_type: int
    model: str = "gemini-2.5-flash"
    user_group: str = ""
    translation_params: TranslationParams | None = None
    summarization_params: SummarizationParams | None = None


class BatchGetTaskRequest(BaseModel):
    task_ids: list[str] = Field(..., max_length=100)


# ============ 响应 ============


class CreateTaskResponse(BaseModel):
    task_id: str
    status: int
    created_at: str


class GetTaskResponse(BaseModel):
    """
    任务详情响应。

    使用自定义序列化以匹配 protobuf JSON 输出：
    - None / 空字符串字段不返回
    - translation_output 和 summarization_output 互斥
    """

    task_id: str
    task_type: int
    status: int
    model: str
    user_group: str = ""
    error_message: str = ""
    translation_output: TranslationOutput | None = None
    summarization_output: SummarizationOutput | None = None
    created_at: str = ""
    updated_at: str = ""
    finished_at: str = ""

    def model_post_init(self, __context: Any) -> None:
        pass

    def to_dict(self) -> dict[str, Any]:
        """序列化为 dict，省略零值字段以匹配 protobuf JSON"""
        d: dict[str, Any] = {
            "task_id": self.task_id,
            "task_type": self.task_type,
            "status": self.status,
            "model": self.model,
        }
        if self.user_group:
            d["user_group"] = self.user_group
        if self.error_message:
            d["error_message"] = self.error_message
        if self.translation_output is not None:
            d["translation_output"] = self.translation_output.model_dump()
        if self.summarization_output is not None:
            d["summarization_output"] = self.summarization_output.model_dump()
        if self.created_at:
            d["created_at"] = self.created_at
        if self.updated_at:
            d["updated_at"] = self.updated_at
        if self.finished_at:
            d["finished_at"] = self.finished_at
        return d


class BatchGetTaskResponse(BaseModel):
    tasks: list[dict[str, Any]]
