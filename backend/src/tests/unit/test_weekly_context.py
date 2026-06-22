"""Unit tests for weekly context data building and formatting (T3, T7).

Verifies: _build_weekly_data returns correct dict structure,
          _format_weekly_context handles all data states,
          constants are used correctly.
"""

from datetime import date

import pytest
from services.reporter import (
    HEADCOUNT_TREND_THRESHOLD,
    MIN_TREND_WEEKS,
    NEGATIVE_RISK_KEYWORDS,
    WeeklyData,
    ReportingService,
)


class TestConstants:
    """T7: Constants are correctly defined and used."""

    def test_negative_keywords_are_list(self):
        assert isinstance(NEGATIVE_RISK_KEYWORDS, list)
        assert len(NEGATIVE_RISK_KEYWORDS) >= 5
        assert "风险" in NEGATIVE_RISK_KEYWORDS

    def test_headcount_threshold_is_float(self):
        assert isinstance(HEADCOUNT_TREND_THRESHOLD, float)
        assert 0.0 < HEADCOUNT_TREND_THRESHOLD < 1.0

    def test_min_trend_weeks_is_int(self):
        assert isinstance(MIN_TREND_WEEKS, int)
        assert MIN_TREND_WEEKS >= 2


class TestCalcRiskCountsUsesConstants:
    """Verify _calc_risk_counts_from_tasks references NEGATIVE_RISK_KEYWORDS."""

    def test_no_negative_keywords_returns_zero(self):
        from models import TodoItem
        task = TodoItem(
            id=1,
            title="测试",
            intent="测试意图",
            query="测试查询",
            summary="一切正常，企业运行良好",
            sources_summary="无异常",
        )
        result = ReportingService._calc_risk_counts_from_tasks([task])
        assert result["total"] == 0
        assert result["red"] == 0

    def test_single_negative_keyword_triggers_yellow(self):
        from models import TodoItem
        task = TodoItem(
            id=1,
            title="测试",
            intent="测试",
            query="测试",
            summary="企业营收下滑明显，存在违约风险",
            sources_summary="",
        )
        result = ReportingService._calc_risk_counts_from_tasks([task])
        # "下滑" and "违约" and "风险" → 3 hits ≥ 3 → red
        assert result["total"] >= 1


class TestBuildWeeklyData:
    """T3: _build_weekly_data returns correct WeeklyData dict."""

    def test_returns_dict_with_required_keys(self):
        svc = ReportingService.__new__(ReportingService)
        data = svc._build_weekly_data("四川振海保安服务有限公司 2026年6月第2周 贷后监管", [])
        assert isinstance(data, dict)
        assert "enterprise" in data
        assert "industry" in data
        assert "loan_amount" in data
        assert "risk" in data
        assert "headcount_trend" in data
        assert "party_a_signals" in data
        assert data["enterprise"] == "四川振海保安服务有限公司"

    def test_headcount_trend_has_correct_structure(self):
        svc = ReportingService.__new__(ReportingService)
        data = svc._build_weekly_data("测试企业", [])
        trend = data["headcount_trend"]
        assert isinstance(trend, dict)
        assert "status" in trend
        assert trend["status"] == "insufficient"  # stub returns []

    def test_party_a_signals_is_none_by_default(self):
        svc = ReportingService.__new__(ReportingService)
        data = svc._build_weekly_data("测试企业", [])
        assert data["party_a_signals"] is None


class TestFormatWeeklyContext:
    """T3: _format_weekly_context handles all data states."""

    def test_full_data_produces_valid_context(self):
        data = WeeklyData(
            enterprise="测试企业",
            industry="安保服务",
            loan_amount="1000.0",
            report_date="2026-06-22",
            report_period_start="2026-06-15",
            report_period_end="2026-06-22",
            ref_text="企业注册资本1200万元",
            risk={"red": 0, "orange": 0, "yellow": 0, "total": 0},
            headcount_trend={
                "status": "stable",
                "current_avg": 15.0,
                "prior_avg": 14.5,
                "delta_pct": 0.0345,
                "message": "→ 稳定，变化 3.5%",
            },
            party_a_signals=None,
        )
        ctx = ReportingService._format_weekly_context(data)
        assert "测试企业" in ctx
        assert "安保服务" in ctx
        assert "1000.0" in ctx
        assert "15.0" in ctx  # current_avg
        assert "14.5" in ctx  # prior_avg
        assert "3.5%" in ctx   # delta_pct formattederov
        assert "稳定" in ctx
        assert "无相关内容" in ctx  # Party A signals fallback

    def test_insufficient_trend_shows_fallback(self):
        data = WeeklyData(
            enterprise="测试企业",
            industry="安保服务",
            loan_amount="1000.0",
            risk={"red": 0, "orange": 0, "yellow": 0, "total": 0},
            headcount_trend={
                "status": "insufficient",
                "current_avg": None,
                "prior_avg": None,
                "delta_pct": None,
                "message": "数据不足，暂无法生成趋势",
            },
        )
        ctx = ReportingService._format_weekly_context(data)
        assert "数据不足" in ctx
        assert "暂无法生成趋势" in ctx

    def test_missing_fields_do_not_crash(self):
        """Empty data dict → no crash, produces minimal valid context."""
        data = WeeklyData()
        ctx = ReportingService._format_weekly_context(data)
        assert "未知" in ctx
        assert "无相关内容" in ctx

    def test_ref_text_included_when_present(self):
        data = WeeklyData(
            enterprise="测试企业",
            industry="安保",
            loan_amount="500.0",
            risk={"red": 0, "orange": 0, "yellow": 0, "total": 0},
            ref_text="重要参考信息：该企业近期中标3个安保项目",
        )
        ctx = ReportingService._format_weekly_context(data)
        assert "重要参考信息" in ctx
