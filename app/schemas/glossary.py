"""
术语表相关的数据模型
"""

import re

from pydantic import BaseModel, Field


class GlossaryTerm(BaseModel):
    """术语表条目"""

    term_id: str = Field(default="", description="术语 ID")
    term_en: str = Field(..., description="英文术语")
    definition: str = Field(default="", description="术语定义")
    part_of_speech: str = Field(default="", description="词性")
    do_not_translate: bool = Field(default=False, description="是否不翻译")
    translations: dict[str, str] = Field(
        default_factory=dict, description="各语言翻译，键为语言代码"
    )
    source: str = Field(default="", description="术语来源标识")

    def get_translation(self, lang_code: str) -> str | None:
        """获取指定语言的翻译"""
        if self.do_not_translate:
            return self.term_en
        return self.translations.get(lang_code)


class Glossary(BaseModel):
    """术语表"""

    terms: list[GlossaryTerm] = Field(default_factory=list, description="术语列表")
    term_lookup: dict[str, GlossaryTerm] = Field(
        default_factory=dict, description="术语查找索引（小写英文术语 -> 条目）"
    )

    def build_lookup(self) -> None:
        """构建术语查找索引"""
        self.term_lookup = {term.term_en.lower(): term for term in self.terms}

    def find_terms_in_text(self, text: str) -> list[GlossaryTerm]:
        """在文本中查找术语（词边界匹配，`.` 视为词的一部分）"""
        found = []
        text_lower = text.lower()
        for term_key, entry in self.term_lookup.items():
            pattern = r"(?<![a-zA-Z0-9.])" + re.escape(term_key) + r"(?![a-zA-Z0-9.])"
            if re.search(pattern, text_lower):
                found.append(entry)
        return found

    def get_expected_translation(self, term_en: str, target_lang: str) -> str | None:
        """获取术语的预期翻译"""
        entry = self.term_lookup.get(term_en.lower())
        if entry:
            return entry.get_translation(target_lang)
        return None
