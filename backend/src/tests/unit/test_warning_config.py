"""Unit tests for WarningConfig — env-based configuration loading."""

import pytest
from config import WarningConfig


class TestWarningConfigFromEnv:
    """WarningConfig.from_env reads all env vars correctly."""

    def test_defaults_when_no_env(self, monkeypatch):
        """Default values used when no env vars set."""
        for var in [
            "WARNING_CRON_INTERVAL", "WARNING_SOURCE_TIMEOUT",
            "WARNING_KEYWORDS_PATH", "WARNING_RED_MAX_DELAY",
            "WARNING_DAILY_PUSH_TIME", "WARNING_ENABLED_SOURCES",
            "WARNING_LLM_TIMEOUT", "QICHACHA_MCP_TOKEN",
            "DM_USERNAME", "DM_PASSWORD", "THS_USERNAME", "THS_PASSWORD",
            "FEISHU_BOT_TOKEN", "WARNING_API_KEY",
        ]:
            monkeypatch.delenv(var, raising=False)

        cfg = WarningConfig.from_env()
        assert cfg.cron_interval == 7200
        assert cfg.source_timeout == 30
        assert cfg.keywords_path == "./config/keywords.yaml"
        assert cfg.red_max_delay == 300
        assert cfg.daily_push_time == "18:00"
        assert cfg.enabled_sources == "all"
        assert cfg.llm_timeout == 15
        assert cfg.qichacha_token == ""
        assert cfg.dm_username == ""
        assert cfg.dm_password == ""
        assert cfg.ths_username == "dhsybl002"
        assert cfg.ths_password == "5TSc27g4"
        assert cfg.feishu_bot_token == ""
        assert cfg.warning_api_key == ""

    def test_custom_env_values(self, monkeypatch):
        """All env vars overridden."""
        monkeypatch.setenv("WARNING_CRON_INTERVAL", "3600")
        monkeypatch.setenv("WARNING_SOURCE_TIMEOUT", "15")
        monkeypatch.setenv("WARNING_KEYWORDS_PATH", "/custom/keywords.yaml")
        monkeypatch.setenv("WARNING_RED_MAX_DELAY", "120")
        monkeypatch.setenv("WARNING_DAILY_PUSH_TIME", "09:00")
        monkeypatch.setenv("WARNING_ENABLED_SOURCES", "qichacha,ths")
        monkeypatch.setenv("WARNING_LLM_TIMEOUT", "30")
        monkeypatch.setenv("QICHACHA_MCP_TOKEN", "qcc_token_123")
        monkeypatch.setenv("DM_USERNAME", "dm_user")
        monkeypatch.setenv("DM_PASSWORD", "dm_pass")
        monkeypatch.setenv("THS_USERNAME", "custom_ths")
        monkeypatch.setenv("THS_PASSWORD", "custom_pass")
        monkeypatch.setenv("FEISHU_BOT_TOKEN", "feishu_token_xyz")
        monkeypatch.setenv("WARNING_API_KEY", "api_key_secret")

        cfg = WarningConfig.from_env()
        assert cfg.cron_interval == 3600
        assert cfg.source_timeout == 15
        assert cfg.keywords_path == "/custom/keywords.yaml"
        assert cfg.red_max_delay == 120
        assert cfg.daily_push_time == "09:00"
        assert cfg.enabled_sources == "qichacha,ths"
        assert cfg.llm_timeout == 30
        assert cfg.qichacha_token == "qcc_token_123"
        assert cfg.dm_username == "dm_user"
        assert cfg.dm_password == "dm_pass"
        assert cfg.ths_username == "custom_ths"
        assert cfg.ths_password == "custom_pass"
        assert cfg.feishu_bot_token == "feishu_token_xyz"
        assert cfg.warning_api_key == "api_key_secret"


class TestSearchAPIEnum:
    """SearchAPI enum additions (LOCAL, BAIDU)."""

    def test_local_and_baidu_are_defined(self):
        from config import SearchAPI
        assert SearchAPI.LOCAL.value == "local"
        assert SearchAPI.BAIDU.value == "baidu"
        assert SearchAPI.LOCAL in list(SearchAPI)
        assert SearchAPI.BAIDU in list(SearchAPI)
