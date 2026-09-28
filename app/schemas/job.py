"""
任务状态相关的数据模型
"""

from datetime import datetime

from pydantic import BaseModel, Field

from app.core.constants import JobStatus
from app.schemas.translation import TranslationRequest, TranslationResponse


class JobProgress(BaseModel):
    """任务进度"""

    total_languages: int = Field(default=0, description="目标语言总数")
    completed_languages: int = Field(default=0, description="已完成的语言数")
    current_phase: str = Field(default="pending", description="当前阶段")
    current_language: str | None = Field(default=None, description="当前处理的语言")
    retry_count: int = Field(default=0, description="当前重试次数")
    # 一致性评审进度（按语言对）
    total_consistency_pairs: int = Field(default=0, description="一致性评审语言对总数")
    completed_consistency_pairs: int = Field(default=0, description="已完成的一致性评审语言对数")
    current_consistency_pair: str | None = Field(default=None, description="当前评审的语言对")

    @property
    def progress_percent(self) -> float:
        """计算进度百分比"""
        if self.total_languages == 0:
            return 0.0
        return (self.completed_languages / self.total_languages) * 100


class JobResult(BaseModel):
    """任务结果"""

    job_id: str = Field(..., description="任务 ID")
    status: JobStatus = Field(..., description="任务状态")
    progress: JobProgress = Field(default_factory=JobProgress, description="任务进度")
    request: TranslationRequest | None = Field(default=None, description="原始请求")
    response: TranslationResponse | None = Field(default=None, description="翻译结果")
    error: str | None = Field(default=None, description="错误信息")
    created_at: datetime = Field(default_factory=datetime.now, description="创建时间")
    updated_at: datetime = Field(default_factory=datetime.now, description="更新时间")
    completed_at: datetime | None = Field(default=None, description="完成时间")


class JobSubmitResponse(BaseModel):
    """任务提交响应"""

    job_id: str = Field(..., description="任务 ID")
    status: JobStatus = Field(..., description="任务状态")
    message: str = Field(default="任务已提交", description="消息")


class JobStatusResponse(BaseModel):
    """任务状态查询响应"""

    job_id: str = Field(..., description="任务 ID")
    status: JobStatus = Field(..., description="任务状态")
    progress: JobProgress = Field(default_factory=JobProgress, description="任务进度")
    response: TranslationResponse | None = Field(default=None, description="翻译结果")
    error: str | None = Field(default=None, description="错误信息")
    created_at: datetime = Field(..., description="创建时间")
    updated_at: datetime = Field(..., description="更新时间")
    completed_at: datetime | None = Field(default=None, description="完成时间")
