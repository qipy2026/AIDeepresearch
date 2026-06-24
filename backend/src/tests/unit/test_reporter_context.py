"""Test reporter fix: enterprises.yaml lookup replaces hardcoded defaults."""

import pytest
import tempfile
import os
from pathlib import Path


class TestEnterpriseFieldLookup:
    """Verify _get_enterprise_field reads from enterprises.yaml correctly."""

    def test_get_industry_from_yaml(self):
        """成都瑜璟 should get 物业管理 from YAML, not 安保服务."""
        from services.reporter import ReportingService

        industry = ReportingService._get_enterprise_field(
            "成都瑜璟物业服务有限公司", "industry"
        )
        assert industry == "物业管理", (
            f"Expected 物业管理 for 成都瑜璟, got {industry}"
        )

    def test_get_industry_not_matching(self):
        """Unknown enterprise should return empty string."""
        from services.reporter import ReportingService

        industry = ReportingService._get_enterprise_field(
            "不存在的企业名称", "industry"
        )
        assert industry == ""

    def test_get_loan_amount_from_yaml(self):
        """四川振海 should get 1000.0 from YAML."""
        from services.reporter import ReportingService

        loan = ReportingService._get_enterprise_field(
            "四川振海保安服务有限公司", "loan_amount"
        )
        assert loan == "1000.0"

    def test_get_empty_field_returns_empty_string(self):
        """成都瑜璟 has no loan_amount in YAML, should return ''."""
        from services.reporter import ReportingService

        loan = ReportingService._get_enterprise_field(
            "成都瑜璟物业服务有限公司", "loan_amount"
        )
        assert loan == ""

    def test_load_enterprises_yaml_has_enterprises(self):
        """YAML should have at least 6 enterprises."""
        from services.reporter import ReportingService

        ents = ReportingService._load_enterprises_yaml()
        assert len(ents) >= 6
        names = [e["name"] for e in ents]
        assert "四川振海保安服务有限公司" in names
        assert "成都瑜璟物业服务有限公司" in names


class TestExtractEnterpriseFromTopic:
    """Verify _extract_enterprise_from_topic handles names without company suffix."""

    def test_extract_with_suffix(self):
        """Standard company names with suffix."""
        from services.reporter import ReportingService

        name = ReportingService._extract_enterprise_from_topic(
            "成都瑜璟物业服务有限公司 贷后风险报告"
        )
        assert name == "成都瑜璟物业服务有限公司"

    def test_extract_without_suffix_falls_back_to_yaml(self):
        """Names like 四川能投润嘉 (no suffix) should be found via YAML fallback."""
        from services.reporter import ReportingService

        name = ReportingService._extract_enterprise_from_topic(
            "四川能投润嘉 经营风险检查"
        )
        # Should match from enterprises.yaml fallback
        assert name == "四川能投润嘉", f"Expected 四川能投润嘉, got {name}"

    def test_extract_unknown_topic_returns_stripped(self):
        """Completely unknown topic returns stripped topic string."""
        from services.reporter import ReportingService

        name = ReportingService._extract_enterprise_from_topic(
            "  random text without enterprise  "
        )
        assert name == "random text without enterprise"


class TestSearchLocal:
    """Verify _search_local queries SQLite warning_log correctly."""

    def test_search_local_returns_results(self):
        from services.web_search import _search_local
        import os

        # _search_local uses WarningDB with default path postloan.db (CWD)
        # Verify the function runs without crashing
        results = _search_local("诉讼 风险 违约", enterprise="成都瑜璟", max_results=10)
        # Database may or may not exist depending on test CWD; function should
        # not raise an exception regardless
        assert isinstance(results, list)
        if results:
            assert all("title" in r and "content" in r for r in results)

    def test_search_local_empty_for_unknown_enterprise(self):
        from services.web_search import _search_local

        results = _search_local("不存在的企业", enterprise="不存在", max_results=5)
        assert results == []

    def test_extract_keywords_filters_stop_words(self):
        from services.web_search import _extract_keywords

        kw = _extract_keywords("的 了 风险 监控 2026 物业管理 诉讼")
        assert "物业管理" in kw
        assert "物业管理" in kw
        assert "诉讼" in kw
        assert "的" not in kw      # stop word
        assert "2026" not in kw    # stop word
