"""
视觉评审相关的数据模型

定义视觉评审请求、响应和中间结果
"""

from pydantic import BaseModel, Field


class VisualReviewRequest(BaseModel):
    """视觉评审请求"""

    target_langs: list[str] = Field(
        ..., description="目标语言列表", min_length=1
    )
    base_url: str = Field(
        default="https://www.example.com", description="网站基础 URL"
    )
    url_path: str = Field(
        default="/ai", description="语言代码后的路径"
    )
    reference_lang: str = Field(
        default="en-US", description="参考语言代码"
    )
    scroll_positions: int = Field(
        default=1, ge=0, le=10, description="截图滚动次数"
    )
    review_model: str | None = Field(
        default=None, description="评审模型"
    )
    sandbox_resolution: str = Field(
        default="1920x1080", description="沙盒分辨率"
    )


class VisualIssue(BaseModel):
    """视觉问题"""

    issue_type: str = Field(
        ...,
        description="问题类型: truncation|overflow|encoding|layout|untranslated|mistranslation|style",
    )
    severity: str = Field(
        ..., description="严重程度: critical|major|minor"
    )
    location: str = Field(
        ..., description="问题位置描述"
    )
    description: str = Field(
        ..., description="问题描述"
    )
    suggestion: str = Field(
        default="", description="修复建议"
    )


class VisualLanguageReview(BaseModel):
    """单语言视觉评审结果"""

    lang_code: str = Field(..., description="语言代码")
    lang_name: str = Field(..., description="语言名称")
    overall_score: int = Field(
        default=0, ge=0, le=100, description="总体评分"
    )
    layout_score: int = Field(
        default=0, ge=0, le=100, description="布局评分"
    )
    text_rendering_score: int = Field(
        default=0, ge=0, le=100, description="文本渲染评分"
    )
    translation_completeness_score: int = Field(
        default=0, ge=0, le=100, description="翻译完整性评分"
    )
    expression_accuracy_score: int = Field(
        default=0, ge=0, le=100, description="表达准确性评分"
    )
    passed: bool = Field(default=False, description="是否通过")
    issues: list[VisualIssue] = Field(
        default_factory=list, description="问题列表"
    )
    screenshots_count: int = Field(
        default=0, description="截图数量"
    )
    feedback: str = Field(default="", description="评审反馈")


class VisualReviewResponse(BaseModel):
    """视觉评审响应"""

    reviews: list[VisualLanguageReview] = Field(
        default_factory=list, description="各语言评审结果"
    )
    reference_lang: str = Field(..., description="参考语言")
    total_languages: int = Field(default=0, description="评审语言总数")
    passed_count: int = Field(default=0, description="通过数量")
    failed_count: int = Field(default=0, description="失败数量")
    total_latency_ms: float = Field(default=0.0, description="总耗时（毫秒）")
    sandbox_error: str | None = Field(
        default=None, description="沙盒错误信息"
    )
