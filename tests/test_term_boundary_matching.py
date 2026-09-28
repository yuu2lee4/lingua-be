"""
术语边界匹配单元测试

验证 `.` 被视为词的一部分，防止 "Liq.Price" 部分匹配 "Est.Liq.Price"
"""

import json
import pytest
import pytest_asyncio

from app.schemas.glossary import GlossaryTerm, Glossary
from app.services.binance_glossary_service import BinanceGlossaryService
from app.agents.translation_agent import TranslationAgent


# ============ Glossary.find_terms_in_text() 边界测试 ============


class TestGlossaryFindTermsBoundary:
    """测试 Glossary.find_terms_in_text() 的边界匹配"""

    def _build_glossary(self, terms: list[str]) -> Glossary:
        glossary = Glossary(
            terms=[GlossaryTerm(term_en=t, translations={"ja-JP": f"翻译_{t}"}) for t in terms]
        )
        glossary.build_lookup()
        return glossary

    def test_dot_prefix_blocks_partial_match(self):
        """'Liq.Price' 不应匹配 'Est.Liq.Price'"""
        glossary = self._build_glossary(["Liq.Price"])
        found = glossary.find_terms_in_text("Est.Liq.Price")
        found_names = [t.term_en for t in found]
        assert "Liq.Price" not in found_names

    def test_full_term_matches(self):
        """'Est.Liq.Price' 应完整匹配"""
        glossary = self._build_glossary(["Est.Liq.Price"])
        found = glossary.find_terms_in_text("The Est.Liq.Price is 100")
        found_names = [t.term_en for t in found]
        assert "Est.Liq.Price" in found_names

    def test_standalone_term_matches(self):
        """独立出现的 'Liq.Price' 应匹配"""
        glossary = self._build_glossary(["Liq.Price"])
        found = glossary.find_terms_in_text("The Liq.Price is 100")
        found_names = [t.term_en for t in found]
        assert "Liq.Price" in found_names

    def test_term_at_start_matches(self):
        """行首的 'Liq.Price' 应匹配"""
        glossary = self._build_glossary(["Liq.Price"])
        found = glossary.find_terms_in_text("Liq.Price is here")
        found_names = [t.term_en for t in found]
        assert "Liq.Price" in found_names

    def test_term_at_end_matches(self):
        """行尾的 'Liq.Price' 应匹配"""
        glossary = self._build_glossary(["Liq.Price"])
        found = glossary.find_terms_in_text("See Liq.Price")
        found_names = [t.term_en for t in found]
        assert "Liq.Price" in found_names

    def test_both_terms_correct(self):
        """同时存在 'Est.Liq.Price' 和 'Liq.Price' 时只匹配完整的"""
        glossary = self._build_glossary(["Liq.Price", "Est.Liq.Price"])
        found = glossary.find_terms_in_text("Check Est.Liq.Price now")
        found_names = [t.term_en for t in found]
        assert "Est.Liq.Price" in found_names
        assert "Liq.Price" not in found_names

    def test_digit_boundary_blocks_partial(self):
        """数字边界也应阻止部分匹配"""
        glossary = self._build_glossary(["Price"])
        found = glossary.find_terms_in_text("Price123")
        found_names = [t.term_en for t in found]
        assert "Price" not in found_names

    def test_case_insensitive(self):
        """匹配应忽略大小写"""
        glossary = self._build_glossary(["Liq.Price"])
        found = glossary.find_terms_in_text("the liq.price is low")
        found_names = [t.term_en for t in found]
        assert "Liq.Price" in found_names


# ============ BinanceGlossaryService.get_direct_matches() 边界测试 ============


BOUNDARY_TEST_DATA = {
    "metadata": {"total_terms": 3},
    "terms": [
        {
            "term_id": "liq_price",
            "term_en": "Liq.Price",
            "source": "binance.com",
            "translations": {"ja-JP": "ロスカット価格", "zh-CN": "强平价格"},
        },
        {
            "term_id": "est_liq_price",
            "term_en": "Est.Liq.Price",
            "source": "binance.com",
            "translations": {"ja-JP": "推定ロスカット価格", "zh-CN": "预估强平价格"},
        },
        {
            "term_id": "deposit",
            "term_en": "Deposit",
            "source": "binance.com",
            "translations": {"ja-JP": "入金", "zh-CN": "充值"},
        },
    ],
}


@pytest.fixture
def boundary_json_file(tmp_path):
    file_path = tmp_path / "test_boundary.json"
    with open(file_path, "w", encoding="utf-8") as f:
        json.dump(BOUNDARY_TEST_DATA, f, ensure_ascii=False)
    return file_path


@pytest_asyncio.fixture
async def boundary_service(boundary_json_file):
    service = BinanceGlossaryService()
    await service.load(boundary_json_file)
    return service


class TestBinanceDirectMatchesBoundary:
    """测试 BinanceGlossaryService.get_direct_matches() 的 `.` 边界"""

    @pytest.mark.asyncio
    async def test_no_partial_match_with_dot(self, boundary_service):
        """'Liq.Price' 不应匹配 'Est.Liq.Price'"""
        matches = boundary_service.get_direct_matches("Est.Liq.Price", "ja-JP")
        assert "Liq.Price" not in matches and "liq.price" not in {
            k.lower() for k in matches
        }

    @pytest.mark.asyncio
    async def test_full_match_with_dot(self, boundary_service):
        """'Est.Liq.Price' 应完整匹配"""
        matches = boundary_service.get_direct_matches("Check Est.Liq.Price now", "ja-JP")
        matched_lower = {k.lower() for k in matches}
        assert "est.liq.price" in matched_lower

    @pytest.mark.asyncio
    async def test_standalone_dot_term_matches(self, boundary_service):
        """独立出现的 'Liq.Price' 应匹配"""
        matches = boundary_service.get_direct_matches("The Liq.Price is 100", "ja-JP")
        matched_lower = {k.lower() for k in matches}
        assert "liq.price" in matched_lower

    @pytest.mark.asyncio
    async def test_both_terms_in_text(self, boundary_service):
        """两个术语在不同位置都应正确匹配"""
        matches = boundary_service.get_direct_matches(
            "Est.Liq.Price is 50, Liq.Price is 100", "ja-JP"
        )
        matched_lower = {k.lower() for k in matches}
        assert "est.liq.price" in matched_lower
        assert "liq.price" in matched_lower


# ============ TranslationAgent._apply_direct_matches() 边界测试 ============


class TestApplyDirectMatchesBoundary:
    """测试 _apply_direct_matches() 的边界匹配"""

    def _make_agent(self) -> TranslationAgent:
        return TranslationAgent(
            target_lang="ja-JP",
            use_two_tier_glossary=False,
        )

    def test_dot_boundary_prevents_false_replacement(self):
        """不应在 'Est.Liq.Price' 中误替换 'Liq.Price' 部分"""
        agent = self._make_agent()
        result = agent._apply_direct_matches(
            translated_text="Est.Liq.Price is here",
            direct_matches={"Liq.Price": "ロスカット価格"},
            source_text="Est.Liq.Price is here",
        )
        # 不应把 Est.Liq.Price 中的 Liq.Price 替换
        assert "Est." in result

    def test_standalone_term_gets_replaced(self):
        """独立出现的术语应被替换"""
        agent = self._make_agent()
        result = agent._apply_direct_matches(
            translated_text="Liq.Price is here",
            direct_matches={"Liq.Price": "ロスカット価格"},
            source_text="Liq.Price is here",
        )
        assert "ロスカット価格" in result
