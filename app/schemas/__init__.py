"""
数据模型模块

包含所有 Pydantic 模型定义
"""

from .glossary import GlossaryTerm, Glossary
from .translation import (
    TranslationRequest,
    TranslationItem,
    TranslationResponse,
)
from .job import (
    JobProgress,
    JobResult,
    JobSubmitResponse,
    JobStatusResponse,
)
from .review import (
    QualityScore,
    QualityReviewResult,
    TermConsistencyIssue,
    ConsistencyReviewResult,
    ReviewFeedback,
)
from .visual_review import (
    VisualReviewRequest,
    VisualReviewResponse,
    VisualLanguageReview,
    VisualIssue,
)

__all__ = [
    # Glossary
    "GlossaryTerm",
    "Glossary",
    # Translation
    "TranslationRequest",
    "TranslationItem",
    "TranslationResponse",
    # Job
    "JobProgress",
    "JobResult",
    "JobSubmitResponse",
    "JobStatusResponse",
    # Review
    "QualityScore",
    "QualityReviewResult",
    "TermConsistencyIssue",
    "ConsistencyReviewResult",
    "ReviewFeedback",
    # Visual Review
    "VisualReviewRequest",
    "VisualReviewResponse",
    "VisualLanguageReview",
    "VisualIssue",
]
