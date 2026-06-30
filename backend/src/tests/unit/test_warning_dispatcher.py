"""Unit tests for warning_dispatcher — Feishu push alerts.

Covers: _send_markdown, push_alert, push_batch.
"""

import subprocess
from unittest.mock import patch, MagicMock

import pytest
from services.warning_dispatcher import push_alert, push_batch, _send_markdown


class TestSendMarkdown:
    """_send_markdown — subprocess integration with lark-cli."""

    def test_successful_send_returns_true(self):
        with patch("subprocess.run") as mock_run:
            mock_result = MagicMock()
            mock_result.returncode = 0
            mock_result.stdout = '{"ok":true}'
            mock_run.return_value = mock_result

            assert _send_markdown("chat_123", "test markdown") is True
            mock_run.assert_called_once()

    def test_nonzero_return_returns_false(self):
        with patch("subprocess.run") as mock_run:
            mock_result = MagicMock()
            mock_result.returncode = 1
            mock_result.stderr = "auth error"
            mock_run.return_value = mock_result

            assert _send_markdown("chat_123", "test") is False

    def test_timeout_returns_false(self):
        with patch("subprocess.run") as mock_run:
            mock_run.side_effect = subprocess.TimeoutExpired(cmd="test", timeout=15)

            assert _send_markdown("chat_123", "test") is False

    def test_generic_exception_returns_false(self):
        with patch("subprocess.run") as mock_run:
            mock_run.side_effect = OSError("broken pipe")

            assert _send_markdown("chat_123", "test") is False


class TestPushAlert:
    """push_alert — severity formatting and no-chat-id fallback."""

    def test_no_chat_id_returns_false(self, monkeypatch):
        monkeypatch.delenv("WARNING_FEISHU_CHAT_ID", raising=False)
        assert push_alert("test_ent", "red", "title", "detail") is False

    def test_red_severity_includes_urgent_suffix(self, monkeypatch):
        monkeypatch.setenv("WARNING_FEISHU_CHAT_ID", "chat_red")
        with patch("services.warning_dispatcher._send_markdown", return_value=True) as mock_send:
            assert push_alert("enterpriseA", "red", "Test Title", "Test detail",
                              source="qichacha", suggested_action="立即处理") is True
            call_args = mock_send.call_args[0]
            assert "chat_red" in call_args
            assert "⚠️ 请立即处理" in call_args[1]

    def test_orange_severity_omits_urgent_suffix(self, monkeypatch):
        monkeypatch.setenv("WARNING_FEISHU_CHAT_ID", "chat_orange")
        with patch("services.warning_dispatcher._send_markdown", return_value=True) as mock_send:
            assert push_alert("entB", "orange", "Title", "detail") is True
            call_args = mock_send.call_args[0]
            assert "⚠️ 请立即处理" not in call_args[1]

    def test_unknown_severity_uses_yellow_emoji(self, monkeypatch):
        monkeypatch.setenv("WARNING_FEISHU_CHAT_ID", "chat_unknown")
        with patch("services.warning_dispatcher._send_markdown", return_value=True) as mock_send:
            assert push_alert("entC", "yellow", "T", "d") is True
            call_args = mock_send.call_args[0]
            assert "🟡" in call_args[1]

    def test_detail_truncated_to_400_chars(self, monkeypatch):
        monkeypatch.setenv("WARNING_FEISHU_CHAT_ID", "chat_trunc")
        with patch("services.warning_dispatcher._send_markdown", return_value=True) as mock_send:
            long_detail = "x" * 500
            assert push_alert("ent", "red", "T", long_detail) is True
            call_args = mock_send.call_args[0]
            assert len([l for l in call_args[1].split("\n") if l.startswith("x")][0]) <= 400

    def test_optional_fields_omitted_when_empty(self, monkeypatch):
        monkeypatch.setenv("WARNING_FEISHU_CHAT_ID", "chat_opt")
        with patch("services.warning_dispatcher._send_markdown", return_value=True) as mock_send:
            assert push_alert("ent", "orange", "Title", "detail", source="", suggested_action="") is True
            call_args = mock_send.call_args[0]
            assert "📡" not in call_args[1]
            assert "💡" not in call_args[1]

    def test_push_send_failure_returns_false(self, monkeypatch):
        monkeypatch.setenv("WARNING_FEISHU_CHAT_ID", "chat_fail")
        with patch("services.warning_dispatcher._send_markdown", return_value=False):
            assert push_alert("ent", "red", "T", "d") is False


class TestPushBatch:
    """push_batch — batch dispatch counting."""

    def test_empty_list_returns_zero(self):
        assert push_batch([]) == 0

    def test_all_succeed_returns_count(self, monkeypatch):
        monkeypatch.setenv("WARNING_FEISHU_CHAT_ID", "chat_batch")
        with patch("services.warning_dispatcher._send_markdown", return_value=True):
            alerts = [
                {"enterprise": "a", "severity": "red", "title": "t1", "detail": "d1"},
                {"enterprise": "b", "severity": "orange", "title": "t2", "detail": "d2"},
            ]
            assert push_batch(alerts) == 2

    def test_partial_failure_counts_correctly(self, monkeypatch):
        monkeypatch.setenv("WARNING_FEISHU_CHAT_ID", "chat_partial")
        call_count = [0]

        def _mock_send(*args, **kwargs):
            call_count[0] += 1
            return call_count[0] != 2  # second call fails

        with patch("services.warning_dispatcher._send_markdown", side_effect=_mock_send):
            alerts = [
                {"enterprise": "a", "severity": "red", "title": "t1", "detail": "d1"},
                {"enterprise": "b", "severity": "orange", "title": "t2", "detail": "d2"},
                {"enterprise": "c", "severity": "yellow", "title": "t3", "detail": "d3"},
            ]
            assert push_batch(alerts) == 2
