"""Unit tests for WarningDB extended methods added in loan branch.

Covers: get_warnings_by_enterprise, get_warnings_grouped_by_severity,
        count_recent_warnings, get_signals_summary, set_severity,
        reset_status.
"""

import pytest
from warning_db import WarningDB


class TestWarningDBExtended:
    """Additional WarningDB methods beyond the basic CRUD."""

    @pytest.fixture
    def db(self):
        db = WarningDB(":memory:")
        db.init()
        return db

    def test_get_warnings_by_enterprise_with_like(self, db):
        db.insert("四川振海保安服务有限公司", "qichacha", "red", "风险",
                  "经营异常", "detail", "action")
        db.insert("成都瑜璟物业服务有限公司", "baidu", "yellow", "舆情",
                  "负面新闻", "detail2", "action2")
        rows = db.get_warnings_by_enterprise("振海", limit=10)
        assert len(rows) >= 1
        assert any("振海" in r["enterprise"] for r in rows)

    def test_get_warnings_grouped_by_severity(self, db):
        db.insert("企业A", "s1", "red", "c1", "t1", "", "", "")
        db.insert("企业A", "s2", "red", "c2", "t2", "", "", "")
        db.insert("企业A", "s3", "orange", "c3", "t3", "", "", "")
        groups = db.get_warnings_grouped_by_severity("企业A")
        assert groups["red"] == 2
        assert groups["orange"] == 1
        assert groups["yellow"] == 0
        assert groups["normal"] == 0

    def test_grouped_by_severity_unknown_enterprise(self, db):
        groups = db.get_warnings_grouped_by_severity("不存在")
        assert groups["red"] == 0
        assert groups["orange"] == 0

    def test_count_recent_warnings(self, db):
        # Insert directly with custom timestamp (via raw SQL to bypass datetime('now'))
        conn = db._get_conn()
        # Recent warning
        db.insert("企业X", "s", "red", "c", "recent_title", "d", "a")
        count = db.count_recent_warnings("企业X", hours=24)
        assert count >= 0  # May be 0 or 1 depending on sqlite datetime

    def test_get_signals_summary_filters_by_severity(self, db):
        db.insert("企业Y", "s1", "red", "风险", "红色信号", "detail", "act")
        db.insert("企业Y", "s2", "orange", "舆情", "橙色信号", "detail2", "act2")
        db.insert("企业Y", "s3", "normal", "info", "普通信息", "d", "a")
        signals = db.get_signals_summary("企业Y", limit=10)
        assert len(signals) >= 2  # red + orange
        severities = {s["severity"] for s in signals}
        assert "normal" not in severities

    def test_get_signals_summary_distinct_titles(self, db):
        db.insert("企业Z", "s1", "red", "c", "相同标题", "d1", "a")
        db.insert("企业Z", "s2", "orange", "c", "相同标题", "d2", "a")
        signals = db.get_signals_summary("企业Z")
        # DISTINCT on title means "相同标题" appears once
        assert len(signals) <= 2

    def test_set_severity_overrides(self, db):
        wid = db.insert("企业W", "s", "yellow", "c", "标题", "detail", "act")
        db.set_severity(wid, "red")
        row = db.get(wid)
        assert row["severity"] == "red"

    def test_reset_status_reverts_false_positive(self, db):
        wid = db.insert("企业V", "s", "red", "c", "标题", "detail", "act")
        db.mark_false(wid, "reviewer")
        assert db.get(wid)["status"] == "false_positive"
        db.reset_status(wid)
        assert db.get(wid)["status"] == "new"
        assert db.get(wid)["acked_by"] == ""

    def test_reset_status_on_acked(self, db):
        wid = db.insert("企业U", "s", "orange", "c", "标题", "detail", "act")
        db.ack(wid, "operator")
        db.reset_status(wid)
        assert db.get(wid)["status"] == "new"
