"""
术语表数据库相关的 Pydantic 模型

用于 API 请求/响应和数据库操作
"""

from datetime import datetime
from enum import Enum

from pydantic import BaseModel, Field


class TermSource(str, Enum):
    """术语来源"""

    MANUAL = "manual"
    AI_EXTRACTED = "ai_extracted"
    IMPORTED = "imported"


class TermStatus(str, Enum):
    """术语状态"""

    ACTIVE = "active"
    INACTIVE = "inactive"
    PENDING = "pending"


class CandidateStatus(str, Enum):
    """候选术语状态"""

    PENDING = "pending"
    APPROVED = "approved"
    REJECTED = "rejected"
    MIGRATED = "migrated"  # 已迁移到正式术语库


# ============ 术语相关模型 ============


class GlossaryTermCreate(BaseModel):
    """创建术语请求"""

    term_en: str = Field(..., min_length=1, max_length=512, description="英文术语")
    definition: str = Field(default="", description="术语定义")
    part_of_speech: str = Field(default="", max_length=32, description="词性")
    do_not_translate: bool = Field(default=False, description="是否不翻译")
    translations: dict[str, str] = Field(
        default_factory=dict, description="各语言翻译，键为语言代码"
    )
    source: TermSource = Field(default=TermSource.MANUAL, description="术语来源")


class GlossaryTermUpdate(BaseModel):
    """更新术语请求"""

    definition: str | None = Field(default=None, description="术语定义")
    part_of_speech: str | None = Field(default=None, description="词性")
    do_not_translate: bool | None = Field(default=None, description="是否不翻译")
    status: TermStatus | None = Field(default=None, description="术语状态")


class GlossaryTermDB(BaseModel):
    """数据库术语记录"""

    id: int
    term_id: str
    term_en: str
    definition: str
    part_of_speech: str
    do_not_translate: bool
    source: str
    status: str
    created_at: datetime
    updated_at: datetime


class GlossaryTermResponse(BaseModel):
    """术语响应模型"""

    term_id: str = Field(..., description="术语 ID")
    term_en: str = Field(..., description="英文术语")
    definition: str = Field(default="", description="术语定义")
    part_of_speech: str = Field(default="", description="词性")
    do_not_translate: bool = Field(default=False, description="是否不翻译")
    translations: dict[str, str] = Field(
        default_factory=dict, description="各语言翻译"
    )
    source: str = Field(default="manual", description="术语来源")
    status: str = Field(default="active", description="术语状态")
    created_at: datetime | None = Field(default=None, description="创建时间")
    updated_at: datetime | None = Field(default=None, description="更新时间")


class GlossaryTermListResponse(BaseModel):
    """术语列表响应"""

    total: int = Field(..., description="总数")
    items: list[GlossaryTermResponse] = Field(default_factory=list, description="术语列表")
    page: int = Field(default=1, description="当前页")
    page_size: int = Field(default=20, description="每页数量")


# ============ 翻译相关模型 ============


class TranslationUpdate(BaseModel):
    """更新翻译请求"""

    translation: str = Field(..., min_length=1, max_length=1024, description="翻译内容")


# ============ 候选术语相关模型 ============


class GlossaryCandidateCreate(BaseModel):
    """创建候选术语请求"""

    term_en: str = Field(..., min_length=1, max_length=512, description="英文术语")
    definition: str = Field(default="", description="术语定义/语境说明")
    part_of_speech: str = Field(default="", max_length=32, description="词性")
    do_not_translate: bool = Field(default=False, description="是否不翻译")
    translations: dict[str, str] = Field(
        default_factory=dict, description="各语言翻译"
    )
    source: TermSource = Field(default=TermSource.AI_EXTRACTED, description="术语来源")


class GlossaryCandidateDB(BaseModel):
    """数据库候选术语记录"""

    id: int
    term_id: str
    term_en: str
    definition: str | None
    part_of_speech: str | None
    do_not_translate: bool
    translations: dict[str, str] | None
    source: str
    status: str
    migrated_to_match_glossary: bool
    migrated_to_business_glossary: bool
    created_at: datetime
    updated_at: datetime


class GlossaryCandidateResponse(BaseModel):
    """候选术语响应模型"""

    id: int = Field(..., description="候选术语 ID")
    term_id: str = Field(..., description="术语 ID")
    term_en: str = Field(..., description="英文术语")
    definition: str = Field(default="", description="术语定义/语境说明")
    part_of_speech: str = Field(default="", description="词性")
    do_not_translate: bool = Field(default=False, description="是否不翻译")
    translations: dict[str, str] = Field(
        default_factory=dict, description="各语言翻译"
    )
    source: str = Field(default="ai_extracted", description="术语来源")
    status: str = Field(default="pending", description="状态")
    migrated_to_match_glossary: bool = Field(
        default=False, description="是否已迁移到 Match Glossary"
    )
    migrated_to_business_glossary: bool = Field(
        default=False, description="是否已迁移到 Business Glossary"
    )
    created_at: datetime | None = Field(default=None, description="创建时间")
    updated_at: datetime | None = Field(default=None, description="更新时间")


class GlossaryCandidateListResponse(BaseModel):
    """候选术语列表响应"""

    total: int = Field(..., description="总数")
    items: list[GlossaryCandidateResponse] = Field(
        default_factory=list, description="候选术语列表"
    )
    page: int = Field(default=1, description="当前页")
    page_size: int = Field(default=20, description="每页数量")


class CandidateReviewRequest(BaseModel):
    """审核候选术语请求"""

    action: CandidateStatus = Field(..., description="审核操作: approved/rejected")
    translations: dict[str, str] | None = Field(
        default=None, description="确认的翻译（批准时使用）"
    )
    migrate_to_match: bool = Field(
        default=False, description="是否迁移到 Match Glossary"
    )
    migrate_to_business: bool = Field(
        default=True, description="是否迁移到 Business Glossary"
    )


# ============ 术语提取相关模型 ============


class GlossaryExtractRequest(BaseModel):
    """AI 术语提取请求"""

    source_text: str = Field(..., min_length=1, description="原文")
    human_translation: str = Field(..., min_length=1, description="人工翻译")
    target_lang: str = Field(..., min_length=2, max_length=16, description="目标语言")
    translation_job_id: str | None = Field(default=None, description="翻译任务 ID")


class ExtractedTerm(BaseModel):
    """提取的术语"""

    term_en: str = Field(..., description="英文术语")
    suggested_translation: str = Field(..., description="建议翻译")
    confidence: float = Field(..., ge=0, le=100, description="置信度")
    context: str = Field(default="", description="上下文")


class GlossaryExtractResponse(BaseModel):
    """AI 术语提取响应"""

    extracted_terms: list[ExtractedTerm] = Field(
        default_factory=list, description="提取的术语列表"
    )
    candidates_created: int = Field(default=0, description="创建的候选术语数量")


# ============ 导入导出相关模型 ============


class GlossaryImportRequest(BaseModel):
    """导入术语表请求"""

    terms: list[GlossaryTermCreate] = Field(..., description="术语列表")
    overwrite: bool = Field(default=False, description="是否覆盖已存在的术语")


class GlossaryImportResponse(BaseModel):
    """导入术语表响应"""

    imported: int = Field(default=0, description="导入成功数量")
    skipped: int = Field(default=0, description="跳过数量")
    errors: list[str] = Field(default_factory=list, description="错误信息列表")


class GlossaryExportResponse(BaseModel):
    """导出术语表响应"""

    terms: list[GlossaryTermResponse] = Field(
        default_factory=list, description="术语列表"
    )
    exported_at: datetime = Field(..., description="导出时间")
    total: int = Field(..., description="总数")


# ============ Two-Tier Glossary Update Models ============


class TranslationFeedbackRequest(BaseModel):
    """
    Translation feedback request for updating glossaries.

    Used by the update-from-translation API endpoint to:
    1. Write source->translation mappings to Match Glossary
    2. Extract business terms via AI to Candidate Glossary
    """

    source_text: str = Field(..., min_length=1, description="Original English text")
    translations: dict[str, str] = Field(
        ...,
        description="Translation results: {lang_code: translated_text}",
        examples=[{"ja-JP": "日本語訳", "ko-KR": "한국어 번역"}],
    )
    translation_job_id: str | None = Field(
        default=None, description="Optional translation job ID for tracking"
    )
    extract_business_terms: bool = Field(
        default=True, description="Whether to extract business terms via AI"
    )


class TranslationFeedbackResponse(BaseModel):
    """Response for translation feedback API."""

    match_glossary_updated: int = Field(
        default=0, description="Number of Match Glossary entries updated"
    )
    candidates_created: int = Field(
        default=0, description="Number of candidate terms created"
    )
    errors: list[str] = Field(
        default_factory=list, description="List of errors encountered"
    )


class MatchGlossaryLookupRequest(BaseModel):
    """Request for direct Match Glossary lookup."""

    term_en: str = Field(..., min_length=1, max_length=512, description="English term")
    target_lang: str = Field(..., min_length=2, max_length=16, description="Target language code")


class MatchGlossaryLookupResponse(BaseModel):
    """Response for Match Glossary lookup."""

    term_en: str = Field(..., description="English term")
    target_lang: str = Field(..., description="Target language code")
    translation: str | None = Field(None, description="Translation if found")
    found: bool = Field(..., description="Whether translation was found")


# ============ Glossary Sync Models (Tolgee Integration) ============


class GlossarySyncTerm(BaseModel):
    """A single glossary term with translations for sync from Tolgee."""

    term_text: str = Field(..., description="Base language term text")
    description: str = Field(default="", description="Term description")
    translations: dict[str, str] = Field(
        default_factory=dict,
        description="Translations keyed by language tag",
    )
    is_non_translatable: bool = Field(default=False)
    is_case_sensitive: bool = Field(default=False)
    is_forbidden_term: bool = Field(default=False)


class GlossarySyncRequest(BaseModel):
    """Request to sync glossary data from Tolgee."""

    glossary_level: str = Field(
        ..., description="Glossary level: L1_MATCH or L2_BUSINESS"
    )
    organization_id: int = Field(..., description="Tolgee organization ID")
    glossary_id: int = Field(..., description="Tolgee glossary ID")
    glossary_name: str = Field(default="", description="Glossary name")
    base_language_tag: str = Field(default="en", description="Base language tag")
    terms: list[GlossarySyncTerm] = Field(
        default_factory=list, description="Terms to sync"
    )


class GlossarySyncResponse(BaseModel):
    """Response for glossary sync."""

    synced: int = Field(default=0, description="Number of terms synced")
    errors: list[str] = Field(default_factory=list, description="Errors encountered")
