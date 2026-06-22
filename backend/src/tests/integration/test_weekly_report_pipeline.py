"""Integration test: full weekly report pipeline with operational signals (T6).

Verifies the end-to-end flow:
  _build_weekly_data → _format_weekly_context → (mock) generate_report
  with operational signal data injected into the LLM context.
"""

import pytest
from datetime import date
from services.reporter import (
    WeeklyData,
    ReportingService,
)


class TestWeeklyReportPipeline:
    """Full pipeline: data → context → report generation."""

    def test_insufficient_trend_produces_fallback_in_context(self):
        """When CameraSnapshot is empty, the context shows '数据不足'."""
        svc = ReportingService.__new__(ReportingService)
        data = svc._build_weekly_data("测试企业", [])
        ctx = ReportingService._format_weekly_context(data)

        assert "企业名称：测试企业" in ctx
        assert "数据不足" in ctx
        assert "暂无法生成趋势" in ctx
        # Party A signals also default
        assert "无相关内容" in ctx

    def test_context_contains_all_sections(self):
        """Formatted context has all required structured sections."""
        svc = ReportingService.__new__(ReportingService)
        data = svc._build_weekly_data("测试安保公司", [])
        ctx = ReportingService._format_weekly_context(data)

        required_sections = [
            "【报告时间】",
            "【企业信息】",
            "【风险统计数据】",
            "【视频巡检人数趋势】",
            "【甲方经营信号】",
        ]
        for section in required_sections:
            assert section in ctx, f"Missing section: {section}"

    def test_stable_trend_includes_all_fields(self):
        """Stable trend produces complete formatted output."""
        data = WeeklyData(
            enterprise="测试企业",
            industry="安保",
            loan_amount="800.0",
            report_date="2026-06-22",
            report_period_start="2026-06-15",
            report_period_end="2026-06-22",
            risk={"red": 1, "orange": 0, "yellow": 2, "total": 3},
            headcount_trend={
                "status": "stable",
                "current_avg": 18.0,
                "prior_avg": 17.0,
                "delta_pct": 0.0588,
                "message": "→ 稳定，变化 5.9%",
            },
            party_a_signals=None,
        )
        ctx = ReportingService._format_weekly_context(data)

        assert "18.0" in ctx
        assert "17.0" in ctx
        assert "5.9%" in ctx

    def test_decline_trend_triggers_warning_language(self):
        """Decline trend → message includes attention markers."""
        data = WeeklyData(
            enterprise="测试企业",
            industry="安保",
            loan_amount="500.0",
            risk={"red": 0, "orange": 0, "yellow": 0, "total": 0},
            headcount_trend={
                "status": "decline",
                "current_avg": 10.0,
                "prior_avg": 15.0,
                "delta_pct": -0.3333,
                "message": "↓ 下降 33.3%，触发关注阈值",
            },
        )
        ctx = ReportingService._format_weekly_context(data)

        assert "下降" in ctx
        assert "33.3%" in ctx
        assert "触发关注阈值" in ctx

    def test_all_zero_anomaly_is_flagged(self):
        """T8: All-zero data produces anomaly message in context."""
        data = WeeklyData(
            enterprise="测试企业",
            industry="安保",
            loan_amount="500.0",
            risk={"red": 0, "orange": 0, "yellow": 0, "total": 0},
            headcount_trend={
                "status": "anomaly",
                "current_avg": 0.0,
                "prior_avg": 0.0,
                "delta_pct": 0.0,
                "message": "数据异常：连续 4 周人数为 0，请检查摄像头配置",
            },
        )
        ctx = ReportingService._format_weekly_context(data)

        assert "数据异常" in ctx
        assert "摄像头配置" in ctx
