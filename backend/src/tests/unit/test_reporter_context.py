"""Test reporter fix: enterprises.yaml lookup replaces hardcoded defaults."""

import pytest
import tempfile
import os
from pathlib import Path


class TestEnterpriseFieldLookup:
    """Verify _get_enterprise_field reads from enterprises.yaml correctly."""

    def test_get_industry_from_yaml(self):
        """成都瑜環 should get 物业管理 from YAML, not 安保服务."""
        from services.reporter import ReportingService

        industry = ReportingService._get_enterprise_field(
            "成都瑜環物业服务有限公司", "industry"
        )
        assert industry == "物业管理", (
            f"Expected 物业管理 for 成都瑜環, got {industry}"
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
        """成都瑜環 has no loan_amount in YAML, should return ''."""
        from services.reporter import ReportingService

        loan = ReportingService._get_enterprise_field(
            "成都瑜環物业服务有限公司", "loan_amount"
        )
        assert loan == ""

    def test_load_enterprises_yaml_has_enterprises(self):
        """YAML should have at least 6 enterprises."""
        from services.reporter import ReportingService

        ents = ReportingService._load_enterprises_yaml()
        assert len(ents) >= 6
        names = [e["name"] for e in ents]
        assert "四川振海保安服务有限公司" in names
        assert "成都瑜環物业服务有限公司" in names


class TestExtractEnterpriseFromTopic:
    """Verify _extract_enterprise_from_topic handles names without company suffix."""

    def test_extract_with_suffix(self):
        """Standard company names with suffix."""
        from services.reporter import ReportingService

        name = ReportingService._extract_enterprise_from_topic(
            "成都瑜環物业服务有限公司 贷后风险报告"
        )
        assert name == "成都瑜環物业服务有限公司"

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


class TestSearchBlocklist:
    """Verify search domain blocklist filters correctly."""

    def test_blocked_domain_is_filtered(self):
        from services.web_search import _is_blocked

        assert _is_blocked("https://ye998.com/page?q=test") is True
        assert _is_blocked("https://www.linkedin.com/jobs/view/12345") is True
        assert _is_blocked("https://www.qs.com/rankings") is True

    def test_normal_domain_passes(self):
        from services.web_search import _is_blocked

        assert _is_blocked("https://news.qq.com/article/123") is False
        assert _is_blocked("https://www.sina.com.cn/finance") is False
        assert _is_blocked("") is False

    def test_blocklist_is_loaded(self):
        from services.web_search import SEARCH_DOMAIN_BLOCKLIST

        assert len(SEARCH_DOMAIN_BLOCKLIST) >= 6
        assert "ye998.com" in SEARCH_DOMAIN_BLOCKLIST
