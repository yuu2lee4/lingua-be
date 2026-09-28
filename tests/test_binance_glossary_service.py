"""
Binance 术语库服务单元测试
"""

import json
import pytest
import pytest_asyncio
from pathlib import Path

from app.services.binance_glossary_service import (
    BinanceGlossaryService,
    _is_quality_term,
)
from app.schemas.glossary import GlossaryTerm


# ============ 测试数据 ============

SAMPLE_DATA = {
    "metadata": {"total_terms": 6, "languages": ["zh-CN", "ja-JP"]},
    "terms": [
        {
            "term_id": "deposit",
            "term_en": "Deposit",
            "source": "binance.com",
            "translations": {
                "zh-CN": "充值",
                "ja-JP": "入金",
                "ko-KR": "입금",
            },
        },
        {
            "term_id": "spot_trading",
            "term_en": "Spot Trading",
            "source": "binance.com",
            "translations": {
                "zh-CN": "现货交易",
                "ja-JP": "現物取引",
                "ko-KR": "현물 거래",
            },
        },
        {
            "term_id": "margin",
            "term_en": "Margin",
            "source": "binance.com",
            "translations": {
                "zh-CN": "杠杆",
                "ja-JP": "マージン",
            },
        },
        {
            # 长字符串 - 不应出现在 L2
            "term_id": "your_withdrawal_has_been_submitted",
            "term_en": "Your withdrawal has been submitted successfully",
            "source": "binance.com",
            "translations": {
                "zh-CN": "您的提现已成功提交",
                "ja-JP": "出金リクエストが送信されました",
            },
        },
        {
            # 包含占位符 - 不应出现在 L2
            "term_id": "amount_placeholder",
            "term_en": "Amount {currency}",
            "source": "binance.com",
            "translations": {
                "zh-CN": "金额 {currency}",
            },
        },
        {
            # 交易对 - 不应出现在 L2
            "term_id": "btc_usdt",
            "term_en": "BTC/USDT",
            "source": "binance.com",
            "translations": {
                "zh-CN": "BTC/USDT",
            },
        },
    ],
}


@pytest.fixture
def sample_json_file(tmp_path):
    """创建测试用的 JSON 文件"""
    file_path = tmp_path / "test_binance_glossary.json"
    with open(file_path, "w", encoding="utf-8") as f:
        json.dump(SAMPLE_DATA, f, ensure_ascii=False)
    return file_path


@pytest_asyncio.fixture
async def loaded_service(sample_json_file):
    """创建并加载好的服务实例"""
    service = BinanceGlossaryService()
    await service.load(sample_json_file)
    return service


# ============ 质量过滤测试 ============


class TestQualityFilter:
    """测试 _is_quality_term 质量过滤函数"""

    def test_short_term_passes(self):
        assert _is_quality_term("Deposit") is True
        assert _is_quality_term("Spot Trading") is True
        assert _is_quality_term("Margin") is True
        assert _is_quality_term("Open Orders") is True

    def test_four_word_term_passes(self):
        assert _is_quality_term("Isolated Margin Mode Settings") is True

    def test_long_term_rejected(self):
        assert _is_quality_term("Your withdrawal has been submitted successfully") is False

    def test_short_string_rejected(self):
        assert _is_quality_term("OK") is False
        assert _is_quality_term("a") is False

    def test_non_alpha_start_rejected(self):
        assert _is_quality_term("123abc") is False
        assert _is_quality_term("{amount}") is False

    def test_placeholder_rejected(self):
        assert _is_quality_term("Amount {currency}") is False
        assert _is_quality_term("Balance $100") is False

    def test_trading_pair_rejected(self):
        assert _is_quality_term("BTC/USDT") is False
        assert _is_quality_term("ETH/BTC pair") is False

    def test_decimal_price_rejected(self):
        assert _is_quality_term("Price 0.001") is False
        assert _is_quality_term("Fee 1.5") is False


# ============ 加载测试 ============


class TestLoad:
    """测试 JSON 加载和 L1/L2 拆分"""

    @pytest.mark.asyncio
    async def test_load_success(self, sample_json_file):
        service = BinanceGlossaryService()
        await service.load(sample_json_file)

        assert service._loaded is True
        assert service.l1_count == 6  # 全部术语
        assert service.l2_count == 3  # Deposit, Spot Trading, Margin

    @pytest.mark.asyncio
    async def test_load_nonexistent_file(self, tmp_path):
        service = BinanceGlossaryService()
        await service.load(tmp_path / "nonexistent.json")

        assert service._loaded is False
        assert service.l1_count == 0

    @pytest.mark.asyncio
    async def test_l2_terms_have_source(self, loaded_service):
        for term in loaded_service._l2_glossary.terms:
            assert term.source == "binance.com"

    @pytest.mark.asyncio
    async def test_first_word_index_built(self, loaded_service):
        index = loaded_service._first_word_index
        assert "deposit" in index
        assert "spot" in index
        assert "margin" in index
        assert "your" in index  # 长字符串的首词也在索引中


# ============ L1 直接匹配测试 ============


class TestGetDirectMatches:
    """测试 L1 直接匹配"""

    @pytest.mark.asyncio
    async def test_basic_match(self, loaded_service):
        matches = loaded_service.get_direct_matches(
            "Please Deposit your funds", "zh-CN"
        )
        assert "Deposit" in matches
        assert matches["Deposit"] == "充值"

    @pytest.mark.asyncio
    async def test_multi_word_match(self, loaded_service):
        matches = loaded_service.get_direct_matches(
            "Go to Spot Trading page", "zh-CN"
        )
        assert any("Spot Trading" in k for k in matches)

    @pytest.mark.asyncio
    async def test_no_match_for_missing_lang(self, loaded_service):
        matches = loaded_service.get_direct_matches(
            "Please Deposit your funds", "fr-FR"
        )
        # fr-FR 不在 sample 翻译中
        assert len(matches) == 0

    @pytest.mark.asyncio
    async def test_no_partial_match(self, loaded_service):
        """不应匹配部分词"""
        matches = loaded_service.get_direct_matches(
            "Depositing funds", "zh-CN"
        )
        # "Deposit" 不应匹配 "Depositing"
        assert "Deposit" not in matches

    @pytest.mark.asyncio
    async def test_not_loaded_returns_empty(self):
        service = BinanceGlossaryService()
        matches = service.get_direct_matches("Deposit", "zh-CN")
        assert matches == {}


# ============ L2 提示词术语测试 ============


class TestGetPromptTerms:
    """测试 L2 提示词术语"""

    @pytest.mark.asyncio
    async def test_basic_prompt_terms(self, loaded_service):
        terms = loaded_service.get_prompt_terms(
            "Deposit and Spot Trading and Margin",
            "zh-CN",
        )
        term_names = [t.term_en for t in terms]
        assert "Deposit" in term_names
        assert "Margin" in term_names
        assert "Spot Trading" in term_names

    @pytest.mark.asyncio
    async def test_exclude_terms(self, loaded_service):
        terms = loaded_service.get_prompt_terms(
            "Deposit and Spot Trading and Margin",
            "zh-CN",
            exclude_terms=["Deposit"],
        )
        term_names = [t.term_en for t in terms]
        assert "Deposit" not in term_names
        assert "Margin" in term_names

    @pytest.mark.asyncio
    async def test_max_terms_limit(self, loaded_service):
        terms = loaded_service.get_prompt_terms(
            "Deposit and Spot Trading and Margin",
            "zh-CN",
            max_terms=1,
        )
        assert len(terms) <= 1

    @pytest.mark.asyncio
    async def test_long_terms_excluded_from_l2(self, loaded_service):
        """长字符串不应出现在 L2 提示词中"""
        terms = loaded_service.get_prompt_terms(
            "Your withdrawal has been submitted successfully",
            "zh-CN",
        )
        term_names = [t.term_en for t in terms]
        assert "Your withdrawal has been submitted successfully" not in term_names

    @pytest.mark.asyncio
    async def test_filters_by_target_lang(self, loaded_service):
        terms = loaded_service.get_prompt_terms(
            "Deposit and Margin",
            "ko-KR",
        )
        # Margin 没有 ko-KR 翻译，只有 Deposit 有
        term_names = [t.term_en for t in terms]
        assert "Deposit" in term_names
        assert "Margin" not in term_names


# ============ L2 Glossary 测试 ============


class TestGetL2Glossary:
    """测试获取 L2 Glossary 对象"""

    @pytest.mark.asyncio
    async def test_returns_glossary(self, loaded_service):
        glossary = loaded_service.get_l2_glossary()
        assert len(glossary.terms) == 3
        assert len(glossary.term_lookup) == 3

    @pytest.mark.asyncio
    async def test_glossary_lookup_works(self, loaded_service):
        glossary = loaded_service.get_l2_glossary()
        result = glossary.get_expected_translation("Deposit", "zh-CN")
        assert result == "充值"
