"""Unit tests for warning classifier (L1 + L2 fallback)."""
import pytest
from services.warning_classifier import ClassifierService


class TestL1KeywordMatching:
    """L1 关键词预筛测试。"""

    @pytest.fixture
    def svc(self):
        return ClassifierService()

    def test_fatal_keyword_returns_red(self, svc):
        result = svc.classify("四川振海保安公司发生重大事故，3人死亡", do_l2=False)
        assert result["severity"] == "red"

    def test_fatal_word_fengcha_returns_red(self, svc):
        result = svc.classify("法院决定查封该公司全部资产", do_l2=False)
        assert result["severity"] == "red"

    def test_severe_keyword_returns_not_none(self, svc):
        result = svc.classify("该企业涉及多起诉讼案件", do_l2=False)
        assert result["severity"] in ("red", "orange", "yellow")

    def test_watch_keyword_returns_not_none(self, svc):
        result = svc.classify("公司营收持续下降", do_l2=False)
        assert result["severity"] in ("red", "orange", "yellow")

    def test_normal_text_returns_none(self, svc):
        result = svc.classify("公司今天正常营业，员工到岗率100%", do_l2=False)
        assert result["severity"] == "none"

    def test_empty_text_returns_none(self, svc):
        result = svc.classify("", do_l2=False)
        assert result["severity"] == "none"

    def test_fatal_priority_over_severe(self, svc):
        # 同时包含致命词和严重词 → 红色
        result = svc.classify("发生重大事故导致企业诉讼缠身", do_l2=False)
        assert result["severity"] == "red"

    def test_result_has_required_fields(self, svc):
        result = svc.classify("企业发生火灾造成重大损失", do_l2=False)
        for field in ("severity", "category", "title", "detail", "suggested_action"):
            assert field in result
