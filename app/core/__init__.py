"""
核心模块

包含常量定义和异常类
"""

from .constants import (
    LanguageCode,
    JobStatus,
    LANGUAGE_NAMES_ZH,
    LANGUAGE_NAMES_EN,
    get_language_name,
    MODEL_CONFIGS,
    AGENT_DEFAULT_MODELS,
    QUALITY_THRESHOLD,
    MAX_RETRIES,
    JOB_TTL_SECONDS,
)
from .exceptions import (
    TranslationServiceError,
    JobNotFoundError,
    JobAlreadyExistsError,
    JobCancelledError,
    TranslationFailedError,
    QualityCheckFailedError,
    LLMClientError,
    GlossaryLoadError,
    MaxRetriesExceededError,
    SandboxError,
    VisualReviewError,
)

__all__ = [
    # Constants
    "LanguageCode",
    "JobStatus",
    "LANGUAGE_NAMES_ZH",
    "LANGUAGE_NAMES_EN",
    "get_language_name",
    "MODEL_CONFIGS",
    "AGENT_DEFAULT_MODELS",
    "QUALITY_THRESHOLD",
    "MAX_RETRIES",
    "JOB_TTL_SECONDS",
    # Exceptions
    "TranslationServiceError",
    "JobNotFoundError",
    "JobAlreadyExistsError",
    "JobCancelledError",
    "TranslationFailedError",
    "QualityCheckFailedError",
    "LLMClientError",
    "GlossaryLoadError",
    "MaxRetriesExceededError",
    "SandboxError",
    "VisualReviewError",
]
