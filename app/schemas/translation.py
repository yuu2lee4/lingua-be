"""
翻译请求和响应的数据模型
"""

from pydantic import BaseModel, Field, model_validator


class TranslationRequest(BaseModel):
    """翻译请求"""

    # 双源字段（新格式）— source_text_1 或 source_text 必须提供其一
    source_text_1: str = Field(default="", description="源文本1（英文）")
    source_lang_1: str = Field(default="en-US", description="源语言1代码")
    source_text_2: str | None = Field(default=None, description="源文本2（中文，可选）")
    source_lang_2: str | None = Field(default=None, description="源语言2代码（可选）")

    # 向后兼容字段
    source_text: str = Field(default="", description="源文本（向后兼容）")
    source_lang: str = Field(default="en-US", description="源语言代码（向后兼容）")

    key: str | None = Field(default=None, description="文本标识键，可提供翻译语境信息")
    target_langs: list[str] = Field(..., description="目标语言代码列表", min_length=1)
    glossary_path: str | None = Field(default=None, description="术语表文件路径")
    translation_model: str | None = Field(default=None, description="翻译模型")
    review_model: str | None = Field(default=None, description="评审模型")
    quality_threshold: int | None = Field(
        default=None, ge=0, le=100, description="质量阈值"
    )
    max_retries: int | None = Field(
        default=None, ge=0, le=5, description="最大重试次数"
    )

    @model_validator(mode="before")
    @classmethod
    def _compat_source_fields(cls, values: dict) -> dict:
        """双向映射新旧字段，保持向后兼容"""
        if isinstance(values, dict):
            # 旧格式 → 新格式：source_text → source_text_1
            if values.get("source_text") and not values.get("source_text_1"):
                values["source_text_1"] = values["source_text"]
            if values.get("source_lang") and not values.get("source_lang_1"):
                values["source_lang_1"] = values["source_lang"]

            # 新格式 → 旧格式：source_text_1 → source_text
            if values.get("source_text_1") and not values.get("source_text"):
                values["source_text"] = values["source_text_1"]
            if values.get("source_lang_1") and not values.get("source_lang"):
                values["source_lang"] = values["source_lang_1"]

            # 验证至少提供了一个源文本（source_text_1 或 source_text_2）
            if (
                not values.get("source_text_1")
                and not values.get("source_text")
                and not values.get("source_text_2")
            ):
                raise ValueError(
                    "At least one source text is required "
                    "(source_text_1, source_text, or source_text_2)"
                )
        return values


class TranslationItem(BaseModel):
    """单个语言的翻译结果"""

    target_lang: str = Field(..., description="目标语言代码")
    translated_text: str = Field(..., description="翻译文本")
    quality_score: int | None = Field(default=None, description="质量评分 (0-100)")
    quality_feedback: str | None = Field(default=None, description="质量评审反馈")
    review_input: str | None = Field(
        default=None, exclude=True, description="评审模型输入（debug）"
    )
    retry_count: int = Field(default=0, description="重试次数")
    latency_ms: float = Field(default=0.0, description="翻译耗时（毫秒）")
    glossary_terms_found: list[str] = Field(
        default_factory=list, description="找到的术语"
    )
    glossary_terms_matched: list[str] = Field(
        default_factory=list, description="匹配的术语"
    )
    glossary_l1_direct_matches: dict[str, str] = Field(
        default_factory=dict, description="L1 术语库强制覆盖的术语 {term_en: translation}"
    )
    placeholder_issues: list[str] = Field(
        default_factory=list, description="占位符校验问题"
    )


class ConsistencyPairResult(BaseModel):
    """语言对一致性评审结果"""

    lang1: str = Field(..., description="语言1代码")
    lang2: str = Field(..., description="语言2代码")
    passed: bool = Field(..., description="是否通过")
    feedback: str = Field(default="", description="评审反馈")
    checked_terms_count: int = Field(default=0, description="检查的术语数量")
    inconsistent_terms_count: int = Field(default=0, description="不一致的术语数量")


class TranslationResponse(BaseModel):
    """翻译响应"""

    # 双源字段（新格式）
    source_text_1: str = Field(default="", description="源文本1（英文）")
    source_lang_1: str = Field(default="en-US", description="源语言1代码")
    source_text_2: str | None = Field(default=None, description="源文本2（中文，可选）")
    source_lang_2: str | None = Field(default=None, description="源语言2代码（可选）")

    # 向后兼容字段
    source_text: str = Field(default="", description="源文本（向后兼容）")
    source_lang: str = Field(default="en-US", description="源语言代码（向后兼容）")

    translations: list[TranslationItem] = Field(
        default_factory=list, description="翻译结果列表"
    )
    # 总体一致性结果（所有语言对都通过则为 True）
    consistency_passed: bool = Field(default=True, description="一致性检查是否通过")
    consistency_feedback: str | None = Field(default=None, description="一致性检查反馈")
    # 按语言对的一致性评审详情
    consistency_pair_results: list[ConsistencyPairResult] = Field(
        default_factory=list, description="语言对一致性评审结果列表"
    )
    total_latency_ms: float = Field(default=0.0, description="总耗时（毫秒）")

    @model_validator(mode="before")
    @classmethod
    def _compat_source_fields(cls, values: dict) -> dict:
        """双向映射新旧字段，保持向后兼容"""
        if isinstance(values, dict):
            if values.get("source_text") and not values.get("source_text_1"):
                values["source_text_1"] = values["source_text"]
            if values.get("source_lang") and not values.get("source_lang_1"):
                values["source_lang_1"] = values["source_lang"]

            if values.get("source_text_1") and not values.get("source_text"):
                values["source_text"] = values["source_text_1"]
            if values.get("source_lang_1") and not values.get("source_lang"):
                values["source_lang"] = values["source_lang_1"]
        return values
