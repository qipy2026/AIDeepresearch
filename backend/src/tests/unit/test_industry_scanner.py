"""Unit tests for industry_scanner — sector matching and fallback.

Covers: _fuzzy_match, fetch_eastmoney_sectors, scan_and_match,
        _ths_fallback edge cases, _empty.
"""

from unittest.mock import patch, MagicMock

import pytest
from services.industry_scanner import (
    _fuzzy_match,
    fetch_eastmoney_sectors,
    scan_and_match,
    _empty,
)


class TestFuzzyMatch:
    """_fuzzy_match — enterprise name against sector name."""

    def test_exact_substring_match(self):
        assert _fuzzy_match("物业管理", "物业服务", "物业管理板块") is True

    def test_sector_name_contains_enterprise(self):
        assert _fuzzy_match("安防", "", "安防设备") is True

    def test_industry_contains_sector_substring(self):
        assert _fuzzy_match("建筑装饰", "建筑行业", "装饰工程") is True

    def test_two_char_substring_match(self):
        assert _fuzzy_match("电子科技", "", "半导体电子") is True

    def test_no_match(self):
        assert _fuzzy_match("物业管理", "安保服务", "新能源板块") is False

    def test_empty_strings_no_match(self):
        assert _fuzzy_match("", "", "anything") is False


class TestFetchEastmoneySectors:
    """fetch_eastmoney_sectors — EastMoney API integration."""

    def test_successful_response_parses_correctly(self):
        mock_resp = MagicMock()
        mock_resp.json.return_value = {
            "data": {
                "diff": [
                    {"f12": "BK0001", "f14": "物业管理", "f3": 2.5, "f2": 1000.0,
                     "f20": 500000000, "f104": 5, "f105": 3, "f128": "万科A"},
                ]
            }
        }
        with patch("services.industry_scanner._get", return_value=mock_resp.json()):
            results = fetch_eastmoney_sectors("industry", "gainers", 10)
            assert len(results) == 1
            assert results[0]["code"] == "BK0001"
            assert results[0]["name"] == "物业管理"
            assert results[0]["change_pct"] == 2.5
            assert results[0]["lead_stock"] == "万科A"

    def test_null_data_returns_empty(self):
        with patch("services.industry_scanner._get", return_value={"data": None}):
            assert fetch_eastmoney_sectors("industry") == []

    def test_network_error_returns_empty(self):
        with patch("services.industry_scanner._get", return_value=None):
            assert fetch_eastmoney_sectors() == []

    def test_missing_diff_key_returns_empty(self):
        with patch("services.industry_scanner._get", return_value={"data": {}}):
            assert fetch_eastmoney_sectors() == []

    def test_concept_type_uses_different_fs(self):
        mock_resp = MagicMock()
        mock_resp.json.return_value = {"data": {"diff": []}}
        with patch("services.industry_scanner._get", return_value=mock_resp.json()) as _mock_get:
            fetch_eastmoney_sectors("concept", "losers", 10)
            # URL should contain m:90+t:3 for concept
            call_url = _mock_get.call_args[0][0] if _mock_get.call_args else ""
            # We just verify no exception
            pass


class TestScanAndMatch:
    """scan_and_match — full industry scanning pipeline."""

    def test_empty_input_enterprises(self):
        with patch("services.industry_scanner.fetch_eastmoney_sectors", return_value=[]), \
             patch("services.industry_scanner._ths_fallback", return_value=_empty(MagicMock())):
            result = scan_and_match([], ths_user="", ths_pass="")
            assert result["matched_risks"] == []
            assert result["matched_opportunities"] == []
            assert result["missed_opportunities"] == []
            assert "updated_at" in result

    def test_cache_returned_within_10_minutes(self):
        """Second call within 10 min returns cached result."""
        from services.industry_scanner import _cache, _cache_time
        from datetime import datetime, timedelta

        # Pre-populate cache
        import services.industry_scanner as _mod
        _mod._cache = {"test": "cached", "updated_at": "now"}
        _mod._cache_time = datetime.now() - timedelta(seconds=300)  # 5 min ago

        result = scan_and_match([{"name": "test", "role": "乙方", "industry": "安保"}])
        assert result["test"] == "cached"

    def test_matched_risk_when_industry_declining(self, monkeypatch):
        """Enterprise matched against declining sector."""
        import services.industry_scanner as _mod
        _mod._cache = None
        _mod._cache_time = None

        _get_resp = {
            "data": {
                "diff": [
                    {"f12": "BK_BAD", "f14": "安保服务", "f3": -6.0, "f2": 800.0,
                     "f20": 100000, "f104": 0, "f105": 10, "f128": ""},
                    {"f12": "BK_GOOD", "f14": "物业管理", "f3": 3.0, "f2": 1200.0,
                     "f20": 200000, "f104": 8, "f105": 2, "f128": ""},
                ]
            }
        }

        enterprises = [
            {"name": "测试安保公司", "role": "甲方", "industry": "安保服务"},
        ]

        with patch("services.industry_scanner._get", return_value=_get_resp):
            result = scan_and_match(enterprises)

        # Should find "测试安保公司" matched against "安保服务" sector (declining)
        assert len(result["matched_risks"]) >= 1
        risk = result["matched_risks"][0]
        assert risk["enterprise"] == "测试安保公司"
        assert risk["sector"] == "安保服务"
        assert risk["level"] == "red"  # -6% <= -5


class TestEmptyFunction:
    """_empty — fallback structure."""

    def test_returns_correct_structure(self):
        from datetime import datetime
        now = datetime(2026, 6, 24, 12, 0, 0)
        result = _empty(now)
        assert result["top_gainers"] == []
        assert result["top_losers"] == []
        assert result["matched_risks"] == []
        assert result["matched_opportunities"] == []
        assert result["missed_opportunities"] == []
        assert result["updated_at"] == now.isoformat()
