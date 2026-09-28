"""
评审相关的数据模型
"""

from pydantic import BaseModel, Field


class QualityScore(BaseModel):
    """质量评分"""

    score: int = Field(..., ge=0, le=100, description="评分 (0-100)")
    accuracy: int = Field(default=0, ge=0, le=100, description="准确性评分")
    fluency: int = Field(default=0, ge=0, le=100, description="流畅性评分")
    terminology: int = Field(default=0, ge=0, le=100, description="术语一致性评分")
    style: int = Field(default=0, ge=0, le=100, description="风格一致性评分")


class QualityReviewResult(BaseModel):
    """质量评审结果"""

    target_lang: str = Field(..., description="目标语言代码")
    source_text: str = Field(..., description="源文本")
    translated_text: str = Field(..., description="翻译文本")
    score: QualityScore = Field(..., description="评分详情")
    passed: bool = Field(..., description="是否通过")
    feedback: str = Field(default="", description="评审反馈")
    suggestions: list[str] = Field(default_factory=list, description="改进建议")


class TermConsistencyIssue(BaseModel):
    """术语一致性问题"""

    term_en: str = Field(..., description="英文术语")
    expected_translations: dict[str, str] = Field(
        default_factory=dict, description="预期翻译（语言代码 -> 翻译）"
    )
    actual_translations: dict[str, str] = Field(
        default_factory=dict, description="实际翻译（语言代码 -> 翻译）"
    )
    issue_description: str = Field(default="", description="问题描述")


class ConsistencyReviewResult(BaseModel):
    """一致性评审结果"""

    passed: bool = Field(..., description="是否通过")
    feedback: str = Field(default="", description="评审反馈")
    issues: list[TermConsistencyIssue] = Field(
        default_factory=list, description="一致性问题列表"
    )
    checked_terms_count: int = Field(default=0, description="检查的术语数量")
    inconsistent_terms_count: int = Field(default=0, description="不一致的术语数量")


class ReviewFeedback(BaseModel):
    """评审反馈（用于重新翻译）"""

    target_lang: str = Field(..., description="目标语言代码")
    original_translation: str = Field(..., description="原始翻译")
    quality_feedback: str | None = Field(default=None, description="质量评审反馈")
    consistency_feedback: str | None = Field(default=None, description="一致性评审反馈")
    suggestions: list[str] = Field(default_factory=list, description="改进建议")
    history: list[dict[str, str]] = Field(
        default_factory=list,
        description="历史重试记录 [{translation, feedback}]",
    )
