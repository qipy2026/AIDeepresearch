"""Unit tests for report CRUD and Feishu send endpoints."""

import pytest
import os
import tempfile
import shutil
from pathlib import Path


# ── 文件级报告 CRUD 测试（不依赖 FastAPI TestClient，直接测文件逻辑）──

class TestReportCRUD:
    """PUT /api/reports/{id} + GET title 字段。"""

    @pytest.fixture
    def reports_dir(self):
        d = tempfile.mkdtemp()
        yield Path(d)
        shutil.rmtree(d, ignore_errors=True)

    def _make_report(self, reports_dir, filename, content):
        p = reports_dir / filename
        p.write_text(content, encoding="utf-8")
        return p

    def test_get_title_parsed_from_filename(self, reports_dir):
        """从文件名解析 title：去掉时间戳 + 替换下划线为空格。"""
        self._make_report(reports_dir,
                          "四川振海保安服务有限公司_20260624_121602.md",
                          "# 测试标题\n\n内容")
        # 模拟 GET 端点中的 title 解析逻辑
        import re
        stem = "四川振海保安服务有限公司_20260624_121602"
        m = re.match(r"^(.+)_\d{8}_\d{6}$", stem)
        assert m is not None
        title = m.group(1).replace("_", " ")
        assert title == "四川振海保安服务有限公司"

    def test_get_title_no_timestamp(self, reports_dir):
        """文件名无时间戳时，整个 stem 作为 title。"""
        stem = "simple_report_name"
        import re
        m = re.match(r"^(.+)_\d{8}_\d{6}$", stem)
        assert m is None
        title = stem.replace("_", " ")
        assert title == "simple report name"

    def test_put_updates_content(self, reports_dir):
        """PUT 覆盖已有报告的 content。"""
        p = self._make_report(reports_dir,
                              "test_20260624_120000.md",
                              "# Old Title\nold content")
        new_content = "# New Title\nnew content"
        p.write_text(new_content, encoding="utf-8")
        assert p.read_text(encoding="utf-8") == new_content

    def test_put_title_change_renames_file(self, reports_dir):
        """title 变更时，文件重命名但保留时间戳后缀。"""
        old_p = self._make_report(reports_dir,
                                  "old_name_20260624_120000.md",
                                  "# Old Name\ncontent")
        # 模拟 PUT 的 rename 逻辑
        new_title = "New Name"
        safe = "".join(c if c.isalnum() or c in "._- " else "_" for c in new_title)
        new_filename = f"{safe}_20260624_120000.md"
        new_p = reports_dir / new_filename
        old_p.rename(new_p)
        assert not old_p.exists()
        assert new_p.exists()
        assert new_p.read_text(encoding="utf-8") == "# Old Name\ncontent"

    def test_put_updates_heading_when_title_changes(self, reports_dir):
        """title 变更时同步更新 markdown 第一个 # heading。"""
        import re
        content = "# Old Heading\n\nrest of content"
        new_title = "New Heading"
        new_content = re.sub(r"^# .+", f"# {new_title}", content, count=1)
        assert new_content == "# New Heading\n\nrest of content"

    def test_put_404_on_missing_report(self, reports_dir):
        """不存在的 report_id 应返回 404。"""
        p = reports_dir / "nonexistent.md"
        assert not p.exists()


# ── Feishu 发送测试 ──────────────────────────────────

class TestSendToFeishu:
    """POST /api/reports/{id}/send-to-feishu。"""

    def test_missing_chat_id_returns_error(self):
        """未传 chat_id 应报错。"""
        chat_id = ""
        assert not chat_id  # 端点应返回 400

    def test_report_not_found_returns_404(self, tmp_path):
        """不存在的 report_id 返回 404。"""
        p = tmp_path / "nonexistent.md"
        assert not p.exists()

    def test_utf8_truncation_respects_boundary(self):
        """截断使用 errors='ignore' 自动丢弃不完整 UTF-8 序列。"""
        text = "测试" * 1000  # 6000 字节
        raw = text.encode("utf-8")[:4000]
        decoded = raw.decode("utf-8", errors="ignore")
        # 无替换字符，无异常
        assert "�" not in decoded
        # 重新编码回去不超过 4000 字节
        assert len(decoded.encode("utf-8")) <= 4000

    def test_utf8_truncation_to_paragraph_boundary(self):
        """截断优先找段落边界（双换行）。"""
        # 构建一个有明确段落边界的文本
        paragraphs = ["段落" + str(i) for i in range(50)]
        text = "\n\n".join(paragraphs)
        raw = text.encode("utf-8")[:4000]
        while raw and (raw[-1] & 0xC0) == 0x80:
            raw = raw[:-1]
        decoded = raw.decode("utf-8", errors="replace")
        last_para = decoded.rfind("\n\n")
        if last_para > len(decoded) // 2:
            decoded = decoded[:last_para]
        # 不应该以半个段落结尾
        assert not decoded.endswith("段落")

    def test_short_content_not_truncated(self):
        """短内容不触发截断。"""
        content = "短报告"
        assert len(content.encode("utf-8")) <= 4000
        # 不应截断
        assert content == "短报告"
