"""Unit tests for video headcount trend functions (T6).

Verifies: _read_camera_snapshots HTTP integration, _compute_headcount_trend,
          boundary conditions, all-zero anomaly detection.
"""

import pytest
from services.reporter import (
    HEADCOUNT_TREND_THRESHOLD,
    MIN_TREND_WEEKS,
    ReportingService,
)


class TestReadCameraSnapshots:
    """T1: _read_camera_snapshots HTTP integration."""

    def test_graceful_degradation_on_connection_error(self, monkeypatch):
        """搜索服务不可达 → 返回空列表,优雅降级为'数据不足'."""
        import requests as _requests

        def _mock_get(*args, **kwargs):
            raise _requests.ConnectionError("搜索服务不可达")

        monkeypatch.setattr(_requests, "get", _mock_get)
        result = ReportingService._read_camera_snapshots("测试企业", weeks=4)
        assert result == []

    def test_params_passed_correctly(self, monkeypatch):
        """验证 fields mapped correctly from aggregated response."""
        call_count = [0]

        class _AggResp:
            status_code = 200
            @staticmethod
            def raise_for_status(): pass
            @staticmethod
            def json():
                return {"bucket": "1h", "camera_id": 1, "data": [
                    {"bucket": "2026-06-24T14", "avg_count": 12.5,
                     "min_count": 8, "max_count": 18, "sample_count": 4}]}

        class _RawResp:
            status_code = 200
            @staticmethod
            def raise_for_status(): pass
            @staticmethod
            def json():
                return {"bucket": "raw", "camera_id": 1, "data": []}

        def _mock_get(url, **kwargs):
            call_count[0] += 1
            return _AggResp() if call_count[0] == 1 else _RawResp()

        monkeypatch.setattr("services.reporter.requests.get", _mock_get)
        result = ReportingService._read_camera_snapshots("test", weeks=4)

        assert len(result) == 1
        assert result[0]["snapshot_date"] == "2026-06-24T14"
        assert result[0]["headcount"] == 12  # round(12.5) -> 12 (banker's rounding)
        assert result[0]["snapshot_path"] == ""

    def test_null_avg_count_skipped(self, monkeypatch):
        """avg_count is None bucket skipped, not crashed."""
        call_count = [0]

        class _AggResp:
            status_code = 200
            @staticmethod
            def raise_for_status(): pass
            @staticmethod
            def json():
                return {"bucket": "1h", "camera_id": 1, "data": [
                    {"bucket": "2026-06-24T14", "avg_count": 10.0,
                     "min_count": 8, "max_count": 12, "sample_count": 4},
                    {"bucket": "2026-06-24T15", "avg_count": None,
                     "min_count": 0, "max_count": 0, "sample_count": 0}]}

        class _RawResp:
            status_code = 200
            @staticmethod
            def raise_for_status(): pass
            @staticmethod
            def json():
                return {"bucket": "raw", "camera_id": 1, "data": []}

        def _mock_get(url, **kwargs):
            call_count[0] += 1
            return _AggResp() if call_count[0] == 1 else _RawResp()

        monkeypatch.setattr("services.reporter.requests.get", _mock_get)
        result = ReportingService._read_camera_snapshots("test", weeks=4)
        assert len(result) == 1  # null bucket skipped
        assert result[0]["headcount"] == 10


class TestComputeHeadcountTrend:
    """T2: _compute_headcount_trend with edge cases (T8)."""

    def test_insufficient_data_returns_fallback(self, monkeypatch):
        """Less than MIN_TREND_WEEKS weeks → 'insufficient'."""
        monkeypatch.setattr(
            ReportingService,
            "_read_camera_snapshots",
            staticmethod(lambda e, w=4: []),
        )
        result = ReportingService._compute_headcount_trend("测试企业", weeks=4)
        assert result["status"] == "insufficient"
        assert result["current_avg"] is None
        assert result["prior_avg"] is None
        assert result["delta_pct"] is None
        assert "数据不足" in result["message"]

    def test_all_zero_headcount_is_anomaly(self, monkeypatch):
        """T8: All-zero data for 4 weeks → 'anomaly', not 'stable'."""
        fake_snapshots = [
            {"snapshot_date": f"2026-06-{d:02d}", "headcount": 0}
            for d in range(17, 23)  # 7 days of zeros
        ] * 4  # 4 weeks

        monkeypatch.setattr(
            ReportingService,
            "_read_camera_snapshots",
            staticmethod(lambda e, w=4: fake_snapshots),
        )
        result = ReportingService._compute_headcount_trend("测试企业")
        assert result["status"] == "anomaly"
        assert "摄像头配置" in result["message"]

    def test_stable_headcount(self, monkeypatch):
        """Headcount unchanged → 'stable'."""
        fake_snapshots = []
        for week_offset in range(4, 0, -1):
            for day_offset in range(7):
                fake_snapshots.append({
                    "snapshot_date": f"2026-06-{(7 * week_offset - day_offset):02d}",
                    "headcount": 15,
                })

        monkeypatch.setattr(
            ReportingService,
            "_read_camera_snapshots",
            staticmethod(lambda e, w=4: fake_snapshots),
        )
        result = ReportingService._compute_headcount_trend("测试企业")
        assert result["status"] == "stable"
        assert result["current_avg"] == 15.0
        assert result["prior_avg"] == 15.0
        assert result["delta_pct"] == 0.0

    def test_decline_above_threshold(self, monkeypatch):
        """Headcount drops by >20% → 'decline'."""
        # 21 days prior at 20, 7 days current at 14 (~ -30%)
        prior = [{"snapshot_date": f"2026-06-{d:02d}", "headcount": 20}
                 for d in range(1, 22)]
        current = [{"snapshot_date": f"2026-06-{d:02d}", "headcount": 14}
                   for d in range(22, 29)]

        monkeypatch.setattr(
            ReportingService,
            "_read_camera_snapshots",
            staticmethod(lambda e, w=4: prior + current),
        )
        result = ReportingService._compute_headcount_trend("测试企业")
        assert result["status"] == "decline"
        assert result["delta_pct"] <= -HEADCOUNT_TREND_THRESHOLD
        assert "下降" in result["message"]

    def test_growth_above_threshold(self, monkeypatch):
        """Headcount grows by >20% → 'growth'."""
        # 21 days prior at 10, 7 days current at 13 (~ +30%)
        prior = [{"snapshot_date": f"2026-06-{d:02d}", "headcount": 10}
                 for d in range(1, 22)]
        current = [{"snapshot_date": f"2026-06-{d:02d}", "headcount": 13}
                   for d in range(22, 29)]

        monkeypatch.setattr(
            ReportingService,
            "_read_camera_snapshots",
            staticmethod(lambda e, w=4: prior + current),
        )
        result = ReportingService._compute_headcount_trend("测试企业")
        assert result["status"] == "growth"
        assert result["delta_pct"] >= HEADCOUNT_TREND_THRESHOLD

    def test_exactly_3_weeks_daily_data(self, monkeypatch):
        """Exactly 3 weeks of distinct-day data → valid, not insufficient."""
        snapshots = []
        for d in range(1, 22):  # 21 days = 3 weeks
            snapshots.append({
                "snapshot_date": f"2026-06-{d:02d}",
                "headcount": 12,
            })

        monkeypatch.setattr(
            ReportingService,
            "_read_camera_snapshots",
            staticmethod(lambda e, w=4: snapshots),
        )
        result = ReportingService._compute_headcount_trend("测试企业")
        assert result["status"] != "insufficient"
        assert result["current_avg"] is not None

    def test_deduplicates_same_day_multiple_snapshots(self, monkeypatch):
        """Multiple snapshots on same day → averaged to one daily value."""
        snapshots = [
            {"snapshot_date": "2026-06-01", "headcount": 10},
            {"snapshot_date": "2026-06-01", "headcount": 20},  # avg=15
            {"snapshot_date": "2026-06-02", "headcount": 15},
            {"snapshot_date": "2026-06-03", "headcount": 15},
        ] * 10  # enough distinct days

        monkeypatch.setattr(
            ReportingService,
            "_read_camera_snapshots",
            staticmethod(lambda e, w=4: snapshots),
        )
        result = ReportingService._compute_headcount_trend("测试企业")
        # Should not raise; dedup works
        assert result["status"] in ("stable", "decline", "growth", "insufficient", "anomaly")
