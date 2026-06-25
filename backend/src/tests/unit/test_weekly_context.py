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

    def test_headcount_trend_has_correct_structure(self, monkeypatch):
        # mock _read_camera_snapshots to return [] (no data available)
        def _mock_empty(*args, **kwargs):
            return []
        monkeypatch.setattr(ReportingService, "_read_camera_snapshots", _mock_empty)
        svc = ReportingService.__new__(ReportingService)
        data = svc._build_weekly_data("测试企业", [])
        trend = data["headcount_trend"]
        assert isinstance(trend, dict)
        assert "status" in trend
        assert trend["status"] == "insufficient"  # no data → fallback

    def test_party_a_signals_is_empty_list_by_default(self):
        """没有配置甲方时 party_a_signals 应为空列表（非 None）。"""
        svc = ReportingService.__new__(ReportingService)
        data = svc._build_weekly_data("测试企业", [])
        assert data["party_a_signals"] == []


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
        assert "暂无甲方经营信号数据" in ctx  # Party A signals fallback

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
        assert "暂无甲方经营信号数据" in ctx

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

    def test_format_weekly_context_with_party_a_signals(self):
        """有甲方信号时上下文包含甲方名称和信号信息。"""
        data = WeeklyData(
            enterprise="乙方测试企业",
            industry="物业管理",
            loan_amount="500.0",
            risk={"red": 0, "orange": 1, "yellow": 2, "total": 3},
            party_a_signals=[
                {
                    "name": "甲方A",
                    "industry": "房地产开发",
                    "parent": "母公司集团",
                    "signals": [
                        {"severity": "red", "title": "严重违约", "detail": "债券违约"},
                        {"severity": "yellow", "title": "经营异常", "detail": "工商变更频繁"},
                    ],
                    "signal_count": 2,
                },
            ],
        )
        ctx = ReportingService._format_weekly_context(data)
        assert "甲方A" in ctx
        assert "房地产开发" in ctx
        assert "2" in ctx  # signal_count
        assert "🔴" in ctx  # max severity

    def test_format_weekly_context_missing_loan_amount(self):
        """loan_amount 为空时显示未披露。"""
        data = WeeklyData(
            enterprise="测试企业",
            loan_amount="未披露",  # 经 _validate_and_enrich 处理后的值
            risk={"red": 0, "orange": 0, "yellow": 0, "total": 0},
        )
        ctx = ReportingService._format_weekly_context(data)
        assert "未披露" in ctx
        assert "发放金额" in ctx


class TestValidateAndEnrich:
    """T7: _validate_and_enrich fills missing fields with defaults."""

    def test_enriches_empty_str_fields(self):
        from services.reporter import FIELD_DEFAULTS
        data = WeeklyData(
            enterprise="测试企业",
            industry="",
            loan_amount="0",
            risk={"red": 0, "orange": 0, "yellow": 0, "total": 0},
        )
        result = ReportingService._validate_and_enrich(data)
        assert result["loan_amount"] == FIELD_DEFAULTS["loan_amount"]
        assert result["industry"] == FIELD_DEFAULTS["industry"]

    def test_enriches_none_list_fields(self):
        data = WeeklyData(
            enterprise="测试企业",
            loan_amount="1000.0",
            risk={"red": 0, "orange": 0, "yellow": 0, "total": 0},
            party_a_signals=None,
            warnings_signals=None,
        )
        result = ReportingService._validate_and_enrich(data)
        assert result["party_a_signals"] == []
        assert result["warnings_signals"] == []

    def test_enriches_none_dict_fields(self):
        data = WeeklyData(
            enterprise="测试企业",
            loan_amount="1000.0",
            risk={"red": 0, "orange": 0, "yellow": 0, "total": 0},
            headcount_trend=None,
            industry_data=None,
        )
        result = ReportingService._validate_and_enrich(data)
        assert result["headcount_trend"] == {"status": "unavailable"}
        assert result["industry_data"] == {"status": "unavailable"}

    def test_does_not_overwrite_valid_data(self):
        valid_signals = [{"name": "甲方A", "signals": [{"severity": "red"}], "signal_count": 1}]
        data = WeeklyData(
            enterprise="测试企业",
            industry="安保服务",
            loan_amount="1000.0",
            risk={"red": 1, "orange": 2, "yellow": 3, "total": 6},
            headcount_trend={"status": "stable", "current_avg": 15.0},
            party_a_signals=valid_signals,
        )
        result = ReportingService._validate_and_enrich(data)
        assert result["loan_amount"] == "1000.0"
        assert result["industry"] == "安保服务"
        assert result["party_a_signals"] == valid_signals
        assert result["headcount_trend"]["status"] == "stable"


class TestFetchPartyASignals:
    """T7: _fetch_party_a_signals fetches party A data from warning_db."""

    def test_returns_empty_list_when_no_parties(self):
        """没有 debtor 指向的甲方时返回空列表。"""
        result = ReportingService._fetch_party_a_signals("不存在的企业")
        assert result == []

    def test_returns_empty_list_when_no_matching_debtor(self, monkeypatch):
        """有企业但无匹配 debtor 时返回空列表。"""
        mock_ents = [
            {"name": "乙方企业", "role": "乙方", "debtor": ""},
            {"name": "甲方A", "role": "甲方", "debtor": "其他企业", "industry": "房地产"},
        ]

        def mock_load():
            return mock_ents

        monkeypatch.setattr(
            ReportingService,
            "_load_enterprises_yaml",
            staticmethod(mock_load),
        )

        result = ReportingService._fetch_party_a_signals("乙方企业")
        assert result == []

    def test_returns_party_a_signals_from_db(self, monkeypatch):
        """有甲方时从 warning_db 拉取信号。"""
        mock_ents = [
            {"name": "乙方企业", "role": "乙方", "debtor": ""},
            {"name": "甲方A", "role": "甲方", "debtor": "乙方企业", "industry": "房地产"},
        ]

        def mock_load():
            return mock_ents

        monkeypatch.setattr(
            ReportingService,
            "_load_enterprises_yaml",
            staticmethod(mock_load),
        )

        # Mock warning_db
        mock_signals = [
            {"severity": "red", "title": "严重违约", "detail": "债券违约"},
        ]

        class MockDB:
            def get_signals_summary(self, enterprise, limit=20):
                if enterprise == "甲方A":
                    return mock_signals
                return []

        monkeypatch.setattr(
            "warning_db.WarningDB",
            MockDB,
        )

        result = ReportingService._fetch_party_a_signals("乙方企业")
        assert len(result) == 1
        assert result[0]["name"] == "甲方A"
        assert result[0]["industry"] == "房地产"
        assert result[0]["signal_count"] == 1
        assert result[0]["signals"][0]["severity"] == "red"
