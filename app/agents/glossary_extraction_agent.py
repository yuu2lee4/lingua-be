"""
术语提取 Agent

基于人工翻译结果，使用 AI 提取潜在的专业术语
"""

import json
import re

from app.agents.base import BaseAgent
from app.logger import logger
from app.schemas.glossary_db import (
    GlossaryExtractRequest,
    GlossaryExtractResponse,
    ExtractedTerm,
    GlossaryCandidateCreate,
)
from app.repositories.glossary_repository import glossary_repository


# 术语提取提示词模板
EXTRACTION_PROMPT = """你是一个专业术语提取专家。请分析以下源文和人工翻译，识别其中的专业术语。

## 任务说明
1. 识别源文中的专业术语、行业用语、专有名词
2. 记录人工翻译中对应的翻译
3. 评估术语的专业性和翻译一致性重要程度

## 提取标准
- 专业术语：特定领域的专业词汇
- 产品名称：品牌、产品、功能名称
- 技术概念：技术术语、API 名称、操作名称
- 行业用语：金融、区块链、交易等行业专用词汇

## 不提取的内容
- 日常用语
- 通用动词和形容词
- 已有明确翻译规范的常见词

## 输入
源文: {source_text}
人工翻译: {human_translation}
目标语言: {target_lang}

## 输出格式
请以 JSON 格式返回，包含以下字段：
```json
{{
  "should_extract": true/false,
  "reason": "是否提取的原因",
  "terms": [
    {{
      "term_en": "英文术语",
      "suggested_translation": "建议翻译",
      "confidence": 置信度(0-100),
      "context": "术语出现的上下文"
    }}
  ]
}}
```

只返回 JSON，不要其他内容。如果没有发现专业术语，should_extract 设为 false，terms 为空数组。
"""


class GlossaryExtractionAgent(BaseAgent):
    """
    术语提取 Agent

    分析人工翻译结果，提取潜在的专业术语
    """

    agent_type: str = "glossary_extraction"

    async def run(
        self,
        request: GlossaryExtractRequest,
    ) -> GlossaryExtractResponse:
        """
        执行术语提取

        Args:
            request: 提取请求

        Returns:
            提取结果
        """
        logger.info(
            f"[GlossaryExtractionAgent.run] 开始提取术语, "
            f"源文长度={len(request.source_text)}, "
            f"目标语言={request.target_lang}"
        )

        # 构建提示词
        prompt = EXTRACTION_PROMPT.format(
            source_text=request.source_text,
            human_translation=request.human_translation,
            target_lang=request.target_lang,
        )

        # 调用 LLM
        messages = [{"role": "user", "content": prompt}]
        response = await self._call_llm(messages, temperature=0.1)

        # 解析响应
        extracted_terms = self._parse_response(response, request)

        # 创建候选术语
        candidates_created = 0
        for term in extracted_terms:
            try:
                candidate = GlossaryCandidateCreate(
                    term_en=term.term_en,
                    definition=term.context,
                    translations={request.target_lang: term.suggested_translation},
                )
                await glossary_repository.create_candidate(candidate)
                candidates_created += 1
            except Exception as e:
                logger.warning(
                    f"[GlossaryExtractionAgent.run] 创建候选术语失败: {term.term_en}, 错误: {e}"
                )

        logger.info(
            f"[GlossaryExtractionAgent.run] 提取完成, "
            f"提取={len(extracted_terms)}, 入库={candidates_created}"
        )

        return GlossaryExtractResponse(
            extracted_terms=extracted_terms,
            candidates_created=candidates_created,
        )

    def _parse_response(
        self,
        response: str,
        request: GlossaryExtractRequest,
    ) -> list[ExtractedTerm]:
        """解析 LLM 响应"""
        try:
            # 尝试提取 JSON
            json_match = re.search(r"\{[\s\S]*\}", response)
            if not json_match:
                logger.warning(
                    f"[GlossaryExtractionAgent._parse_response] 无法提取 JSON"
                )
                return []

            data = json.loads(json_match.group())

            # 检查是否需要提取
            if not data.get("should_extract", False):
                logger.info(
                    f"[GlossaryExtractionAgent._parse_response] 无需提取术语: "
                    f"{data.get('reason', '未说明原因')}"
                )
                return []

            # 解析术语列表
            terms = []
            for item in data.get("terms", []):
                term = ExtractedTerm(
                    term_en=item.get("term_en", ""),
                    suggested_translation=item.get("suggested_translation", ""),
                    confidence=float(item.get("confidence", 50)),
                    context=item.get("context", ""),
                )
                if term.term_en and term.suggested_translation:
                    terms.append(term)

            return terms

        except json.JSONDecodeError as e:
            logger.error(
                f"[GlossaryExtractionAgent._parse_response] JSON 解析失败: {e}"
            )
            return []
        except Exception as e:
            logger.error(
                f"[GlossaryExtractionAgent._parse_response] 解析失败: {e}"
            )
            return []

    async def extract_batch(
        self,
        requests: list[GlossaryExtractRequest],
    ) -> list[GlossaryExtractResponse]:
        """
        批量提取术语

        Args:
            requests: 提取请求列表

        Returns:
            提取结果列表
        """
        results = []
        for request in requests:
            try:
                result = await self.run(request)
                results.append(result)
            except Exception as e:
                logger.error(
                    f"[GlossaryExtractionAgent.extract_batch] 提取失败: {e}"
                )
                results.append(
                    GlossaryExtractResponse(extracted_terms=[], candidates_created=0)
                )
        return results
