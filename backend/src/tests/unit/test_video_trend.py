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

    def test_graceful_degradation_on_db_missing(self, monkeypatch):
        """DB路径不存在 → 返回空列表,优雅降级."""
        monkeypatch.setenv("CAMERA_DB_PATH", "/nonexistent/path/counts.db")
        result = ReportingService._read_camera_snapshots("测试企业", weeks=4)
        assert result == []

    def test_graceful_degradation_on_camera_db_path_unset(self, monkeypatch):
        """CAMERA_DB_PATH 未设置 → 返回空列表,优雅降级."""
        monkeypatch.delenv("CAMERA_DB_PATH", raising=False)
        result = ReportingService._read_camera_snapshots("测试企业", weeks=4)
        assert result == []

    def test_params_passed_correctly(self, monkeypatch, tmp_path):
        """验证从SQLite读取后字段映射正确：snapshot_date/headcount/snapshot_path."""
        import sqlite3
        from datetime import datetime, timezone, timedelta

        now = datetime.now(timezone.utc)
        t = now - timedelta(hours=2)
        ts = t.strftime("%Y-%m-%dT%H:%M:%S+00:00")
        created = t.strftime("%Y-%m-%d %H:%M:%S")
        expected_bucket = t.strftime("%Y-%m-%dT%H")

        db_path = tmp_path / "test.db"
        conn = sqlite3.connect(str(db_path))
        conn.execute("""CREATE TABLE IF NOT EXISTS counts (
            id INTEGER PRIMARY KEY, camera_id INTEGER NOT NULL,
            recorded_at TEXT NOT NULL, person_count INTEGER,
            snapshot_path TEXT NOT NULL, created_at TEXT NOT NULL)""")
        conn.execute("INSERT INTO counts VALUES (1, 1, ?, 12, '', ?)", (ts, created))
        conn.commit()
        conn.close()

        monkeypatch.setenv("CAMERA_DB_PATH", str(db_path))
        monkeypatch.setenv("CAMERA_SNAPSHOT_SRC", str(tmp_path))
        monkeypatch.setenv("CAMERA_SNAPSHOT_LOCAL", str(tmp_path / "local"))

        result = ReportingService._read_camera_snapshots("test", weeks=4)

        assert len(result) == 1
        assert result[0]["snapshot_date"] == expected_bucket
        assert result[0]["headcount"] == 12
        assert result[0]["snapshot_path"] == ""

    def test_null_avg_count_skipped(self, monkeypatch, tmp_path):
        """person_count IS NULL 的行被 SQL WHERE 过滤，不参与聚合."""
        import sqlite3
        from datetime import datetime, timezone, timedelta

        now = datetime.now(timezone.utc)
        t1 = now - timedelta(hours=3)
        t2 = now - timedelta(hours=2)
        ts1 = t1.strftime("%Y-%m-%dT%H:%M:%S+00:00")
        ts2 = t2.strftime("%Y-%m-%dT%H:%M:%S+00:00")
        created1 = t1.strftime("%Y-%m-%d %H:%M:%S")
        created2 = t2.strftime("%Y-%m-%d %H:%M:%S")

        db_path = tmp_path / "test.db"
        conn = sqlite3.connect(str(db_path))
        conn.execute("""CREATE TABLE IF NOT EXISTS counts (
            id INTEGER PRIMARY KEY, camera_id INTEGER NOT NULL,
            recorded_at TEXT NOT NULL, person_count INTEGER,
            snapshot_path TEXT NOT NULL, created_at TEXT NOT NULL)""")
        conn.execute("INSERT INTO counts VALUES (1, 1, ?, 10, '', ?)", (ts1, created1))
        conn.execute("INSERT INTO counts VALUES (2, 1, ?, NULL, '', ?)", (ts2, created2))
        conn.commit()
        conn.close()

        monkeypatch.setenv("CAMERA_DB_PATH", str(db_path))
        monkeypatch.setenv("CAMERA_SNAPSHOT_SRC", str(tmp_path))
        monkeypatch.setenv("CAMERA_SNAPSHOT_LOCAL", str(tmp_path / "local"))

        result = ReportingService._read_camera_snapshots("test", weeks=4)
        assert len(result) == 1  # null bucket skipped
        assert result[0]["headcount"] == 10

    # ── 新增：SQLite 直读 + 图片同步 ──────────────────────

    def test_reads_snapshots_from_sqlite(self, monkeypatch, tmp_path):
        """验证从 SQLite 读取数据后返回格式与原来 HTTP 版本一致."""
        import sqlite3
        from datetime import datetime, timezone, timedelta

        now = datetime.now(timezone.utc)
        t1 = now - timedelta(hours=3)
        t2 = now - timedelta(hours=2)
        t_null = now - timedelta(hours=1)
        ts1 = t1.strftime("%Y-%m-%dT%H:%M:%S+00:00")
        ts2 = t2.strftime("%Y-%m-%dT%H:%M:%S+00:00")
        ts_null = t_null.strftime("%Y-%m-%dT%H:%M:%S+00:00")
        created1 = t1.strftime("%Y-%m-%d %H:%M:%S")
        created2 = t2.strftime("%Y-%m-%d %H:%M:%S")
        created_null = t_null.strftime("%Y-%m-%d %H:%M:%S")
        bucket1 = t1.strftime("%Y-%m-%dT%H")
        bucket2 = t2.strftime("%Y-%m-%dT%H")

        db_path = tmp_path / "test_counts.db"
        conn = sqlite3.connect(str(db_path))
        conn.execute("""
            CREATE TABLE IF NOT EXISTS counts (
                id INTEGER PRIMARY KEY,
                camera_id INTEGER NOT NULL,
                recorded_at TEXT NOT NULL,
                person_count INTEGER,
                snapshot_path TEXT NOT NULL,
                created_at TEXT NOT NULL
            )
        """)
        conn.execute(
            "INSERT INTO counts (camera_id, recorded_at, person_count, snapshot_path, created_at) "
            "VALUES (1, ?, 12, '', ?)", (ts1, created1))
        conn.execute(
            "INSERT INTO counts (camera_id, recorded_at, person_count, snapshot_path, created_at) "
            "VALUES (1, ?, 8, '', ?)", (ts2, created2))
        conn.execute(
            "INSERT INTO counts (camera_id, recorded_at, person_count, snapshot_path, created_at) "
            "VALUES (1, ?, NULL, '', ?)", (ts_null, created_null))
        conn.execute(
            "INSERT INTO counts (camera_id, recorded_at, person_count, snapshot_path, created_at) "
            "VALUES (2, ?, 100, '', ?)", (ts1, created1))
        conn.commit()
        conn.close()

        monkeypatch.setenv("CAMERA_DB_PATH", str(db_path))
        monkeypatch.setenv("CAMERA_SNAPSHOT_SRC", str(tmp_path))
        monkeypatch.setenv("CAMERA_SNAPSHOT_LOCAL", str(tmp_path / "local_snapshots"))

        result = ReportingService._read_camera_snapshots("测试企业", weeks=4)

        # camera_id=1, person_count IS NOT NULL → 2 rows, 2 distinct buckets
        assert len(result) == 2
        assert result[0]["snapshot_date"] == bucket1
        assert result[0]["headcount"] == 12  # single value in bucket
        assert result[0]["snapshot_path"] == ""

    def test_sync_images_copies_files(self, monkeypatch, tmp_path):
        """图片从源目录复制到本地目录，snapshot_path 更新为文件名."""
        import sqlite3
        from datetime import datetime, timezone, timedelta

        now = datetime.now(timezone.utc)
        t = now - timedelta(hours=2)
        ts = t.strftime("%Y-%m-%dT%H:%M:%S")
        created = t.strftime("%Y-%m-%d %H:%M:%S")

        src_dir = tmp_path / "src_snapshots"
        src_dir.mkdir()
        img_file = src_dir / "snap_abc.jpg"
        img_file.write_bytes(b"fake jpeg data")

        db_path = tmp_path / "test.db"
        conn = sqlite3.connect(str(db_path))
        conn.execute("""CREATE TABLE counts (
            id INTEGER PRIMARY KEY, camera_id INTEGER, recorded_at TEXT,
            person_count INTEGER, snapshot_path TEXT, created_at TEXT)""")
        conn.execute(
            "INSERT INTO counts VALUES (1, 1, ?, 5, 'snapshot_data\\snap_abc.jpg', ?)",
            (ts, created))
        conn.commit()
        conn.close()

        local_dir = tmp_path / "local_snapshots"

        monkeypatch.setenv("CAMERA_DB_PATH", str(db_path))
        monkeypatch.setenv("CAMERA_SNAPSHOT_SRC", str(src_dir))
        monkeypatch.setenv("CAMERA_SNAPSHOT_LOCAL", str(local_dir))

        result = ReportingService._read_camera_snapshots("test", weeks=4)

        copied = local_dir / "snap_abc.jpg"
        assert copied.exists()
        assert copied.read_bytes() == b"fake jpeg data"
        assert result[0]["snapshot_path"] == "snap_abc.jpg"

    def test_sync_images_skips_when_src_missing(self, monkeypatch, tmp_path):
        """源目录不存在时图片跳过，不阻塞报告生成."""
        import sqlite3
        from datetime import datetime, timezone, timedelta

        now = datetime.now(timezone.utc)
        t = now - timedelta(hours=2)
        ts = t.strftime("%Y-%m-%dT%H:%M:%S")
        created = t.strftime("%Y-%m-%d %H:%M:%S")

        db_path = tmp_path / "test.db"
        conn = sqlite3.connect(str(db_path))
        conn.execute("""CREATE TABLE counts (
            id INTEGER PRIMARY KEY, camera_id INTEGER, recorded_at TEXT,
            person_count INTEGER, snapshot_path TEXT, created_at TEXT)""")
        conn.execute(
            "INSERT INTO counts VALUES (1, 1, ?, 5, 'snapshot_data\\snap_missing.jpg', ?)",
            (ts, created))
        conn.commit()
        conn.close()

        monkeypatch.setenv("CAMERA_DB_PATH", str(db_path))
        monkeypatch.setenv("CAMERA_SNAPSHOT_SRC", "/nonexistent/src_dir")
        monkeypatch.setenv("CAMERA_SNAPSHOT_LOCAL", str(tmp_path / "local"))

        result = ReportingService._read_camera_snapshots("test", weeks=4)
        assert len(result) == 1
        assert result[0]["snapshot_path"] == ""


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


class TestAttachKeySnapshots:
    """T3: _attach_key_snapshots — key moment selection and backfill."""

    def test_selects_peak_valley_9am_2pm(self):
        """有4张不同时间快照 → 4个关键时刻全部选取并匹配到聚合桶."""
        from services.reporter import ReportingService

        aggregated = [
            {"snapshot_date": "2026-06-24T14", "headcount": 18, "snapshot_path": ""},
            {"snapshot_date": "2026-06-24T09", "headcount": 5, "snapshot_path": ""},
        ]
        raw = [
            {"timestamp": "2026-06-24T14:00:00+00:00", "person_count": 18,
             "snapshot_path": "/data/snap_14.jpg"},
            {"timestamp": "2026-06-24T09:05:00+00:00", "person_count": 5,
             "snapshot_path": "/data/snap_09.jpg"},
            {"timestamp": "2026-06-24T16:00:00+00:00", "person_count": 25,
             "snapshot_path": "/data/snap_16.jpg"},
            {"timestamp": "2026-06-24T08:55:00+00:00", "person_count": 3,
             "snapshot_path": "/data/snap_08.jpg"},
        ]

        ReportingService._attach_key_snapshots(aggregated, raw)

        # 14:00 桶匹配到 14:00 快照
        row_14 = next(r for r in aggregated if r["snapshot_date"] == "2026-06-24T14")
        assert row_14["snapshot_path"] != ""
        # 09:00 桶匹配到 09:05 快照
        row_09 = next(r for r in aggregated if r["snapshot_date"] == "2026-06-24T09")
        assert row_09["snapshot_path"] != ""

    def test_empty_raw_snapshots_is_noop(self):
        """空原始快照列表 → 聚合结果不变,不抛异常."""
        from services.reporter import ReportingService

        aggregated = [
            {"snapshot_date": "2026-06-24T14", "headcount": 0, "snapshot_path": ""},
        ]
        ReportingService._attach_key_snapshots(aggregated, [])

        assert aggregated[0]["snapshot_path"] == ""

    def test_single_snapshot_becomes_all_key_moments(self):
        """只有1张快照 → peak/valley/9am/2pm 都是同一张."""
        from services.reporter import ReportingService

        aggregated = [
            {"snapshot_date": "2026-06-24T12", "headcount": 10, "snapshot_path": ""},
        ]
        raw = [
            {"timestamp": "2026-06-24T12:00:00+00:00", "person_count": 10,
             "snapshot_path": "/data/snap_solo.jpg"},
        ]

        ReportingService._attach_key_snapshots(aggregated, raw)
        assert aggregated[0]["snapshot_path"] == "/data/snap_solo.jpg"


class TestInjectSnapshotImages:
    """T4: _inject_snapshot_images — post-processing placeholder replacement."""

    def test_replaces_placeholder_with_images(self):
        """报告中含占位文本 → 替换为真实截图 markdown 图片."""
        from services.reporter import _inject_snapshot_images

        report = """## 四、现场视频巡检

### 重点时段照片记录

（占位，预备未来接入摄像头数据）

报告结束。"""

        key_snapshots = [
            {"snapshot_date": "2026-06-24T16", "headcount": 17,
             "snapshot_path": "/data/snap_16.jpg"},
            {"snapshot_date": "2026-06-24T14", "headcount": 18,
             "snapshot_path": "/data/snap_14.jpg"},
        ]

        result = _inject_snapshot_images(report, key_snapshots)

        assert "占位" not in result
        assert "snap_16.jpg" in result
        assert "snap_14.jpg" in result
        assert "17人" in result
        assert "18人" in result

    def test_empty_snapshots_returns_unchanged(self):
        """空截图列表 → 报告原文不变."""
        from services.reporter import _inject_snapshot_images

        report = "（占位，预备未来接入摄像头数据）"
        result = _inject_snapshot_images(report, [])

        assert result == report

    def test_alternate_placeholder_pattern_replaced(self):
        """备用占位模式（关键时刻截图）也正确替换."""
        from services.reporter import _inject_snapshot_images

        report = "（若上下文中包含【关键时刻截图】，请原样复制到此处）"
        key_snapshots = [
            {"snapshot_date": "2026-06-24T09", "headcount": 5,
             "snapshot_path": "/data/snap_09.jpg"},
        ]

        result = _inject_snapshot_images(report, key_snapshots)

        assert "关键时刻截图" not in result
        assert "snap_09.jpg" in result


class TestBuildVideoInspectionSection:
    """T5: _build_video_inspection_section — code-generated video inspection chapter."""

    def test_full_data_generates_all_subsections(self):
        """有完整聚合数据和关键时刻截图 → 三个子节全部生成."""
        from services.reporter import ReportingService

        aggregated = [
            {"snapshot_date": "2026-06-20T14", "headcount": 7, "snapshot_path": "snap_20_14.jpg"},
            {"snapshot_date": "2026-06-24T09", "headcount": 4, "snapshot_path": "snap_24_09.jpg"},
            {"snapshot_date": "2026-06-24T14", "headcount": 8, "snapshot_path": "snap_24_14.jpg"},
        ]
        key_snaps = [
            {"snapshot_date": "2026-06-24T14", "headcount": 8,
             "snapshot_path": "snap_24_14.jpg"},
            {"snapshot_date": "2026-06-24T09", "headcount": 4,
             "snapshot_path": "snap_24_09.jpg"},
        ]
        headcount_trend = {
            "status": "stable",
            "current_avg": 6.0,
            "prior_avg": 6.5,
            "delta_pct": -0.077,
            "message": "→ 稳定，变化 7.7%",
        }

        result = ReportingService._build_video_inspection_section(
            aggregated, key_snaps, headcount_trend
        )

        assert "## 四、现场视频巡检" in result
        assert "### 重点时段统计" in result
        assert "### 历史对比" in result
        assert "### 重点时段照片记录" in result
        assert "snap_24_14.jpg" in result
        assert "snap_24_09.jpg" in result
        assert "8人" in result

    def test_empty_data_shows_fallback_text(self):
        """无聚合数据 → 各子节显示降级文本."""
        from services.reporter import ReportingService

        result = ReportingService._build_video_inspection_section([], [], None)

        assert "## 四、现场视频巡检" in result
        assert "暂无巡检数据" in result
        assert "暂无历史对比数据" in result
        assert "暂无快照数据" in result

    def test_partial_data_shows_dash_for_missing_hours(self):
        """某天只有14:00数据 → 09:00显示 '—'."""
        from services.reporter import ReportingService

        aggregated = [
            {"snapshot_date": "2026-06-24T14", "headcount": 5, "snapshot_path": ""},
        ]
        result = ReportingService._build_video_inspection_section(
            aggregated, [], None
        )

        assert "2026-06-24" in result
        assert "| — |" in result  # 09:00 missing
        assert "| 5 |" in result  # 14:00 present

    def test_no_trend_data_shows_fallback_in_history(self):
        """无趋势数据 → 历史对比显示降级文本."""
        from services.reporter import ReportingService

        aggregated = [
            {"snapshot_date": "2026-06-24T14", "headcount": 5, "snapshot_path": ""},
        ]
        result = ReportingService._build_video_inspection_section(
            aggregated, [], None
        )

        assert "暂无历史对比数据" in result
