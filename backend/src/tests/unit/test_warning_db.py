"""Unit tests for WarningDB data model."""
import pytest
from warning_db import WarningDB


class TestWarningDB:
    """warning_log 数据模型测试。"""

    @pytest.fixture
    def db(self):
        db = WarningDB(":memory:")
        db.init()
        return db

    def test_insert_returns_id(self, db):
        wid = db.insert("测试企业", "test", "red", "舆情",
                        title="测试预警", detail="详情",
                        suggested_action="核实", raw_data='{"k":"v"}')
        assert wid > 0

    def test_dedup_same_source_title(self, db):
        wid1 = db.insert("企业", "qichacha", "red", "舆情",
                         "同一标题", "", "", "")
        wid2 = db.insert("企业", "qichacha", "red", "舆情",
                         "同一标题", "", "", "")
        assert wid1 == wid2

    def test_list_warnings(self, db):
        db.insert("企业A", "s1", "red", "c1", "标题1", "", "", "")
        db.insert("企业B", "s2", "yellow", "c2", "标题2", "", "", "")
        rows = db.list_warnings(limit=10)
        assert len(rows) == 2

    def test_ack_sets_status(self, db):
        wid = db.insert("企业", "s", "red", "c", "标题", "", "", "")
        db.ack(wid, "测试员")
        row = db.get(wid)
        assert row["status"] == "acked"
        assert row["acked_by"] == "测试员"

    def test_mark_false_sets_status(self, db):
        wid = db.insert("企业", "s", "orange", "c", "标题", "", "", "")
        db.mark_false(wid, "审核员")
        row = db.get(wid)
        assert row["status"] == "false_positive"

    def test_filter_by_severity(self, db):
        db.insert("A", "s", "red", "c", "t1", "", "", "")
        db.insert("B", "s", "yellow", "c", "t2", "", "", "")
        rows = db.list_warnings(severity="red")
        assert len(rows) == 1
        assert rows[0]["severity"] == "red"

    def test_filter_by_enterprise(self, db):
        db.insert("振海", "s", "red", "c", "t", "", "", "")
        db.insert("中铁建", "s", "red", "c", "t", "", "", "")
        rows = db.list_warnings(enterprise="振海")
        assert len(rows) == 1

    def test_stats_returns_counts(self, db):
        db.insert("A", "s", "red", "c", "t1", "", "", "")
        db.insert("B", "s", "red", "c", "t2", "", "", "")
        db.insert("C", "s", "yellow", "c", "t3", "", "", "")
        s = db.stats()
        assert s["by_severity"]["red"] == 2
        assert s["by_severity"]["yellow"] == 1
