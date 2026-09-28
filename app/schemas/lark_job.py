"""
Lark 电子表格翻译任务的 Pydantic 模型
"""

from enum import Enum

from pydantic import BaseModel, Field


class LarkJobStatus(str, Enum):
    """Lark 翻译任务状态"""

    NEW = "new"  # 新建，待翻译
    TRANSLATED = "translated"  # 已翻译，待审核
    REVIEWED = "reviewed"  # 已审核，待同步术语
    COMPLETED = "completed"  # 已完成
    PROBLEM = "problem"  # 有问题


class LarkSyncResult(BaseModel):
    """Lark 同步结果"""

    total_records: int = Field(default=0, description="总记录数")
    processed: int = Field(default=0, description="已处理数")
    success: int = Field(default=0, description="成功数")
    failed: int = Field(default=0, description="失败数")
    skipped: int = Field(default=0, description="跳过数")
    errors: list[str] = Field(default_factory=list, description="错误信息列表")
