"""
核心常量定义

包含语言代码、模型配置等常量
"""

from enum import Enum


class LanguageCode(str, Enum):
    """支持的语言代码（14 种目标语言）"""

    AR = "ar"
    DE_DE = "de-DE"
    EN_US = "en-US"
    ES_ES = "es-ES"
    FR_FR = "fr-FR"
    ID_ID = "id-ID"
    JA_JP = "ja-JP"
    KO_KR = "ko-KR"
    PT_BR = "pt-BR"
    RU_RU = "ru-RU"
    UK_UA = "uk-UA"
    VI_VN = "vi-VN"
    ZH_CN = "zh-CN"
    ZH_TW = "zh-TW"


class JobStatus(str, Enum):
    """任务状态"""

    PENDING = "pending"
    IN_PROGRESS = "in_progress"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"


# 语言代码到中文名称映射
LANGUAGE_NAMES_ZH: dict[str, str] = {
    "ar": "阿拉伯语",
    "de-DE": "德语",
    "en-US": "英语",
    "es-ES": "西班牙语",
    "fr-FR": "法语",
    "id-ID": "印尼语",
    "ja-JP": "日语",
    "ko-KR": "韩语",
    "pt-BR": "葡萄牙语",
    "ru-RU": "俄语",
    "uk-UA": "乌克兰语",
    "vi-VN": "越南语",
    "zh-CN": "简体中文",
    "zh-TW": "繁体中文",
}

# 语言代码到英文名称映射
LANGUAGE_NAMES_EN: dict[str, str] = {
    "ar": "Arabic",
    "de-DE": "German",
    "en-US": "English",
    "es-ES": "Spanish",
    "fr-FR": "French",
    "id-ID": "Indonesian",
    "ja-JP": "Japanese",
    "ko-KR": "Korean",
    "pt-BR": "Portuguese",
    "ru-RU": "Russian",
    "uk-UA": "Ukrainian",
    "vi-VN": "Vietnamese",
    "zh-CN": "Simplified Chinese",
    "zh-TW": "Traditional Chinese",
}


def get_language_name(lang_code: str, chinese: bool = False) -> str:
    """获取语言名称"""
    mapping = LANGUAGE_NAMES_ZH if chinese else LANGUAGE_NAMES_EN
    return mapping.get(lang_code, lang_code)


# 模型配置 - OpenAI 兼容端点
MODEL_CONFIGS: dict[str, dict[str, str]] = {
    # Anthropic 模型
    "claude-sonnet-4-5-20250929": {
        "base_url": "https://api.anthropic.com/v1/",
        "api_key_env": "ANTHROPIC_API_KEY",
        "provider": "anthropic",
    },
    "claude-opus-4-6": {
        "base_url": "https://api.anthropic.com/v1/",
        "api_key_env": "ANTHROPIC_API_KEY",
        "provider": "anthropic",
    },
    # OpenAI 模型
    "gpt-4o-mini": {
        "base_url": "https://api.openai.com/v1/",
        "api_key_env": "OPENAI_API_KEY",
        "provider": "openai",
    },
    "gpt-5-mini": {
        "base_url": "https://api.openai.com/v1/",
        "api_key_env": "OPENAI_API_KEY",
        "provider": "openai",
    },
    "gpt-5.2": {
        "base_url": "https://api.openai.com/v1/",
        "api_key_env": "OPENAI_API_KEY",
        "provider": "openai",
    },
    # Google 模型
    "gemini-2.5-flash": {
        "base_url": "https://generativelanguage.googleapis.com/v1beta/openai/",
        "api_key_env": "GOOGLE_API_KEY",
        "provider": "google",
    },
    "gemini-3-flash-preview": {
        "base_url": "https://generativelanguage.googleapis.com/v1beta/openai/",
        "api_key_env": "GOOGLE_API_KEY",
        "provider": "google",
    },
    "gemini-3-pro-preview": {
        "base_url": "https://generativelanguage.googleapis.com/v1beta/openai/",
        "api_key_env": "GOOGLE_API_KEY",
        "provider": "google",
    },
}

# 各 Agent 类型默认使用的模型
AGENT_DEFAULT_MODELS: dict[str, str] = {
    "translation": "claude-opus-4-6",
    "quality_review": "gpt-5.2",
    "consistency_review": "gpt-5.2",
    "glossary_extraction": "claude-opus-4-6",
    "visual_review": "claude-sonnet-4-5-20250929",
}

# ============ Task API 常量 ============

# Task API 支持的语言（匹配 Go ai-infra）
TASK_SUPPORTED_LANGUAGES: set[str] = {
    "de-DE", "en-US", "es-ES", "fr-FR", "ja-JP", "pt-BR",
    "ru-RU", "uk-UA", "vi-VN", "zh-CN", "zh-TW",
    "ar", "nl-NL", "tr-TR", "ko-KR",
}

# Task API 语言代码到中文名称映射（用于 AI prompt）
TASK_LANGUAGE_NAMES_ZH: dict[str, str] = {
    "de-DE": "德语",
    "en-US": "英语",
    "es-ES": "西班牙语",
    "fr-FR": "法语",
    "ja-JP": "日语",
    "pt-BR": "葡萄牙语",
    "ru-RU": "俄语",
    "uk-UA": "乌克兰语",
    "vi-VN": "越南语",
    "zh-CN": "简体中文",
    "zh-TW": "繁体中文",
    "ar": "阿拉伯语",
    "nl-NL": "荷兰语",
    "tr-TR": "土耳其语",
    "ko-KR": "韩语",
}

# Task API 默认处理模型
TASK_DEFAULT_MODEL: str = "gemini-2.5-flash"

# 翻译质量阈值
QUALITY_THRESHOLD: int = 95

# 最大重试次数
MAX_RETRIES: int = 2

# Job TTL（秒）
JOB_TTL_SECONDS: int = 3600  # 1 小时
