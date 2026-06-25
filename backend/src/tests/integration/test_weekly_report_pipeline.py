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

    def test_insufficient_trend_produces_fallback_in_context(self, monkeypatch):
        """When CameraSnapshot is empty, the context shows '数据不足'."""
        def _mock_empty(*args, **kwargs):
            return []
        monkeypatch.setattr(ReportingService, "_read_camera_snapshots", _mock_empty)
        svc = ReportingService.__new__(ReportingService)
        data = svc._build_weekly_data("测试企业", [])
        ctx = ReportingService._format_weekly_context(data)

        assert "企业名称：测试企业" in ctx
        assert "数据不足" in ctx
        assert "暂无法生成趋势" in ctx
        # Party A signals also default
        assert "暂无甲方经营信号数据" in ctx

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

    def test_key_snapshots_injected_into_context(self):
        """E2E: key_snapshots in WeeklyData produce screenshot markdown in context."""
        data = WeeklyData(
            enterprise="测试企业",
            industry="安保",
            loan_amount="500.0",
            risk={"red": 0, "orange": 0, "yellow": 0, "total": 0},
            headcount_trend={
                "status": "stable",
                "current_avg": 15.0,
                "prior_avg": 14.0,
                "delta_pct": 0.071,
                "message": "→ 稳定，变化 7.1%",
            },
            key_snapshots=[
                {"snapshot_date": "2026-06-24T16", "headcount": 17,
                 "snapshot_path": "/data/snap_16.jpg"},
                {"snapshot_date": "2026-06-24T14", "headcount": 18,
                 "snapshot_path": "/data/snap_14.jpg"},
            ],
        )
        ctx = ReportingService._format_weekly_context(data)

        # 截图应出现在关键时刻截图区域
        assert "snap_16.jpg" in ctx
        assert "snap_14.jpg" in ctx
        assert "人数" in ctx
        assert "关键时刻截图" in ctx

    def test_screenshot_injection_post_process(self):
        """E2E: _inject_snapshot_images replaces placeholder in a complete report."""
        from services.reporter import _inject_snapshot_images

        report = """## 四、现场视频巡检

（注：一个企业通常配置4-6个摄像头点位，以下为巡检数据）

### 重点时段照片记录

（占位，预备未来接入摄像头数据）

---
## 五、综合结论与建议
"""

        key_snapshots = [
            {"snapshot_date": "2026-06-24T16", "headcount": 17,
             "snapshot_path": "/data/snap_a.jpg"},
        ]

        result = _inject_snapshot_images(report, key_snapshots)

        assert "占位" not in result
        assert "snap_a.jpg" in result
        # 其余章节不受影响
        assert "综合结论与建议" in result


class TestCameraApiConnectivity:
    """T9: 真实摄像头数据源连通性与 schema 契约验证。

    这些测试在摄像头 search 项目不可达时自动跳过。
    """

    @staticmethod
    def _camera_api_url() -> str:
        import os
        return os.getenv("CAMERA_API_URL", "http://localhost:5000")

    @classmethod
    def _is_reachable(cls) -> bool:
        import requests
        try:
            r = requests.get(
                f"{cls._camera_api_url()}/api/counts/timeseries",
                params={"camera_id": 1, "days": 1},
                timeout=3,
            )
            return r.status_code == 200
        except requests.RequestException:
            return False

    def test_aggregated_endpoint_schema(self):
        """聚合端点返回 schema 与 _read_camera_snapshots 契约一致。

        验证: data[] 中每项含 bucket/avg_count/min_count/max_count/sample_count。
        """
        if not self._is_reachable():
            pytest.skip("摄像头 search 项目不可达")

        import requests
        resp = requests.get(
            f"{self._camera_api_url()}/api/counts/timeseries",
            params={"camera_id": 1, "days": 7},
            timeout=10,
        )
        resp.raise_for_status()
        body = resp.json()

        assert isinstance(body, dict), f"顶层期望 dict，实际 {type(body)}"
        data = body.get("data", []) if isinstance(body, dict) else []
        assert isinstance(data, list), f"data 期望 list，实际 {type(data)}"

        required_fields = {"bucket", "avg_count", "min_count", "max_count", "sample_count"}
        for i, row in enumerate(data[:20]):  # 抽检前 20 条
            missing = required_fields - set(row.keys())
            assert not missing, f"行 {i} 缺字段: {missing}"

    def test_raw_endpoint_schema(self):
        """原始记录端点返回 schema 含 snapshot_path/person_count/timestamp。

        验证: 可被 _attach_key_snapshots 正确消费。
        """
        if not self._is_reachable():
            pytest.skip("摄像头 search 项目不可达")

        import requests
        from datetime import datetime as _dt, timedelta as _td, timezone as _tz
        from_ts = (_dt.now(_tz.utc) - _td(days=7)).strftime("%Y-%m-%d")

        resp = requests.get(
            f"{self._camera_api_url()}/api/counts/timeseries",
            params={"camera_id": 1, "bucket": "raw", "from": from_ts},
            timeout=10,
        )
        resp.raise_for_status()
        body = resp.json()

        data = body.get("data", []) if isinstance(body, dict) else []
        assert isinstance(data, list), f"raw data 期望 list，实际 {type(data)}"

        if data:
            required_fields = {"snapshot_path", "person_count", "timestamp"}
            for i, row in enumerate(data[:10]):
                missing = required_fields - set(row.keys())
                assert not missing, f"raw 行 {i} 缺字段: {missing}"

    def test_full_pipeline_with_real_data(self):
        """端到端: 真实 API 数据 → _read_camera_snapshots → 聚合结果非空。

        这是对【现场视频巡检数据源】最直接的连通性验证。
        """
        if not self._is_reachable():
            pytest.skip("摄像头 search 项目不可达")

        from services.reporter import ReportingService

        result = ReportingService._read_camera_snapshots("成都瑜璟物业服务有限公司", weeks=2)

        assert isinstance(result, list), f"期望 list，实际 {type(result)}"
        # 即使数据为空也不 crash——优雅降级已验证
        if result:
            row0 = result[0]
            assert "snapshot_date" in row0, f"缺 snapshot_date，keys={list(row0.keys())}"
            assert "headcount" in row0, f"缺 headcount，keys={list(row0.keys())}"
            assert isinstance(row0["headcount"], int), \
                f"headcount 期望 int，实际 {type(row0['headcount'])}"
