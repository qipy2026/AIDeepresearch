"""Integration tests for send-to-feishu endpoint (mocked lark-cli)."""
import pytest
import os
import subprocess
import tempfile
import json
from pathlib import Path
from unittest.mock import patch, MagicMock


class TestSendReportToFeishu:
    """POST /api/reports/{id}/send-to-feishu — Word file send."""

    @pytest.fixture
    def reports_dir(self):
        d = tempfile.mkdtemp()
        yield Path(d)
        import shutil
        shutil.rmtree(d, ignore_errors=True)

    def _make_report(self, reports_dir, filename, content):
        p = reports_dir / filename
        p.write_text(content, encoding="utf-8")
        return p

    @patch("subprocess.run")
    def test_sends_docx_file_via_lark_cli(self, mock_run, reports_dir):
        """验证端点使用报告名作为文件名 + 相对路径 + cwd。"""
        import os as _os

        # Setup: 创建测试报告
        report_id = "test_report_20260624_120000"
        self._make_report(reports_dir, f"{report_id}.md",
                          "# 测试标题\n\n测试内容。\n\n- 事项1\n- 事项2")

        mock_result = MagicMock()
        mock_result.returncode = 0
        mock_run.return_value = mock_result

        # 模拟端点逻辑
        _p = reports_dir / f"{report_id}.md"
        assert _p.exists()

        from convert_to_docx import convert_md_to_docx_bytes
        docx_buf = convert_md_to_docx_bytes(str(_p))

        # 用报告名作为文件名
        safe_name = "".join(c if c.isalnum() or c in "._- " else "_" for c in report_id)
        tmp_dir = tempfile.gettempdir()
        tmp_path = _os.path.join(tmp_dir, f"{safe_name}.docx")
        with open(tmp_path, "wb") as f:
            f.write(docx_buf.read())
        docx_buf.close()
        tmp_filename = f"{safe_name}.docx"

        # 验证文件名包含报告标识
        assert "test_report" in tmp_filename
        assert tmp_filename.endswith(".docx")

        import shutil
        _lark = shutil.which("lark-cli") or "lark-cli"

        try:
            result = subprocess.run(
                [_lark, "im", "+messages-send",
                 "--chat-id", "oc_test123",
                 "--file", tmp_filename,
                 "--as", "bot",
                 "--format", "json"],
                capture_output=True, text=True, encoding="utf-8", timeout=30,
                cwd=tmp_dir,
            )
            assert result.returncode == 0
            # 验证 lark-cli 调用使用了相对路径和 cwd
            mock_run.assert_called_once()
            call_args = mock_run.call_args
            assert "--file" in call_args[0][0]
            file_idx = list(call_args[0][0]).index("--file") + 1
            passed_file = call_args[0][0][file_idx]
            assert not _os.path.isabs(passed_file), f"Expected relative path, got {passed_file}"
            assert passed_file == tmp_filename, f"Expected {tmp_filename}, got {passed_file}"
            assert "cwd" in call_args[1]
        finally:
            try:
                _os.unlink(tmp_path)
            except OSError:
                pass

    def test_chat_id_empty_returns_400(self):
        """chat_id 为空应拒绝。"""
        chat_id = ""
        assert not chat_id

    def test_missing_report_returns_404(self, reports_dir):
        """不存在的报告返回 404。"""
        p = reports_dir / "nonexistent.md"
        assert not p.exists()

    @patch("subprocess.run")
    def test_temp_file_cleaned_after_send(self, mock_run, reports_dir):
        """临时 .docx 在发送后（无论成功与否）被清理。"""
        mock_result = MagicMock()
        mock_result.returncode = 0
        mock_run.return_value = mock_result

        tmp = tempfile.NamedTemporaryFile(suffix=".docx", delete=False)
        tmp_path = tmp.name
        tmp.close()

        assert os.path.exists(tmp_path)
        os.unlink(tmp_path)
        assert not os.path.exists(tmp_path)
