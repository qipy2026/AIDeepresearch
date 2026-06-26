"""Unit tests for web_search — baidu, duckduckgo, dispatch_search routing."""

from unittest.mock import patch, MagicMock

import pytest
from services.web_search import _search_baidu, _search_duckduckgo, dispatch_search
from config import Configuration, SearchAPI


# ── _search_baidu ─────────────────────────────────────────────────

class TestSearchBaidu:
    """百度千帆 AI 搜索。"""

    def test_returns_empty_when_token_missing(self, monkeypatch):
        """未配置 BAIDU_ACCESS_TOKEN 时返回空列表。"""
        monkeypatch.delenv("BAIDU_ACCESS_TOKEN", raising=False)
        results = _search_baidu("测试查询")
        assert results == []

    @patch("services.web_search.requests")
    def test_successful_search_returns_parsed_results(self, mock_requests):
        """正常返回时解析 title/url/content。"""
        mock_resp = MagicMock()
        mock_resp.raise_for_status.return_value = None
        mock_resp.json.return_value = {
            "references": [
                {
                    "title": "百度搜索修复方案",
                    "url": "https://example.com/1",
                    "content": "这是摘要内容",
                },
                {
                    "title": "第二条结果",
                    "url": "https://example.com/2",
                    "content": "第二条摘要",
                },
            ]
        }
        mock_requests.post.return_value = mock_resp

        with patch.dict("os.environ", {"BAIDU_ACCESS_TOKEN": "test-token"}):
            results = _search_baidu("测试查询", max_results=2)

        assert len(results) == 2
        assert results[0] == {
            "title": "百度搜索修复方案",
            "url": "https://example.com/1",
            "content": "这是摘要内容",
        }
        assert results[1]["title"] == "第二条结果"

        # 验证调用了正确的 API
        mock_requests.post.assert_called_once()
        call_args = mock_requests.post.call_args
        assert call_args[0][0] == "https://qianfan.baidubce.com/v2/ai_search/web_search"
        assert call_args[1]["headers"]["Authorization"] == "Bearer test-token"
        assert call_args[1]["json"]["messages"][0]["content"] == "测试查询"
        assert call_args[1]["json"]["search_source"] == "baidu_search_v2"
        assert call_args[1]["timeout"] == 30

    @patch("services.web_search.requests")
    def test_api_error_returns_empty(self, mock_requests):
        """API 调用失败时返回空列表，不抛异常。"""
        mock_requests.post.side_effect = Exception("Connection refused")

        with patch.dict("os.environ", {"BAIDU_ACCESS_TOKEN": "test-token"}):
            results = _search_baidu("测试查询")

        assert results == []

    @patch("services.web_search.requests")
    def test_respects_max_results(self, mock_requests):
        """返回结果不超过 max_results。"""
        mock_resp = MagicMock()
        mock_resp.raise_for_status.return_value = None
        mock_resp.json.return_value = {
            "references": [
                {"title": f"结果{i}", "url": f"https://e/{i}", "content": f"摘要{i}"}
                for i in range(10)
            ]
        }
        mock_requests.post.return_value = mock_resp

        with patch.dict("os.environ", {"BAIDU_ACCESS_TOKEN": "test-token"}):
            results = _search_baidu("测试查询", max_results=3)

        assert len(results) == 3

    @patch("services.web_search.requests")
    def test_empty_search_results(self, mock_requests):
        """API 返回空 references 时返回空列表。"""
        mock_resp = MagicMock()
        mock_resp.raise_for_status.return_value = None
        mock_resp.json.return_value = {"references": None}

        with patch.dict("os.environ", {"BAIDU_ACCESS_TOKEN": "test-token"}):
            results = _search_baidu("测试查询")

        assert results == []

    @patch("services.web_search.requests")
    def test_content_field(self, mock_requests):
        """正常解析 content 字段。"""
        mock_resp = MagicMock()
        mock_resp.raise_for_status.return_value = None
        mock_resp.json.return_value = {
            "references": [
                {"title": "标题", "url": "https://e.com/1", "content": "正文内容"},
            ]
        }
        mock_requests.post.return_value = mock_resp

        with patch.dict("os.environ", {"BAIDU_ACCESS_TOKEN": "test-token"}):
            results = _search_baidu("查询")

        assert results[0]["content"] == "正文内容"


# ── _search_duckduckgo ────────────────────────────────────────────

class TestSearchDuckDuckGo:
    """DuckDuckGo 搜索。"""

    @patch("ddgs.DDGS")
    def test_successful_search(self, mock_ddgs_cls):
        """正常返回时解析 title/href/body。"""
        mock_ddgs = MagicMock()
        mock_ddgs_cls.return_value.__enter__.return_value = mock_ddgs
        mock_ddgs.text.return_value = [
            {"title": "DDG结果1", "href": "https://d.com/1", "body": "内容1"},
            {"title": "DDG结果2", "href": "https://d.com/2", "body": "内容2"},
        ]

        results = _search_duckduckgo("测试", max_results=5)

        assert len(results) == 2
        assert results[0] == {
            "title": "DDG结果1",
            "url": "https://d.com/1",
            "content": "内容1",
        }
        mock_ddgs.text.assert_called_once_with("测试", max_results=5)

    @patch("ddgs.DDGS")
    def test_api_error_returns_empty(self, mock_ddgs_cls):
        """DDGS 异常时返回空列表。"""
        mock_ddgs_cls.side_effect = Exception("DDGS unavailable")

        results = _search_duckduckgo("测试")

        assert results == []


# ── dispatch_search 路由 ──────────────────────────────────────────

class TestDispatchSearch:
    """dispatch_search 路由分发。"""

    @patch("services.web_search._search_baidu")
    def test_routes_baidu(self, mock_baidu):
        """search_api=baidu 时走 _search_baidu。"""
        mock_baidu.return_value = [
            {"title": "百度", "url": "https://b.com", "content": "内容"}
        ]
        config = Configuration(search_api=SearchAPI.BAIDU)

        payload, notices, answer, backend = dispatch_search("查询", config, 0)

        assert backend == "baidu"
        assert len(payload["results"]) == 1
        mock_baidu.assert_called_once()

    @patch("services.web_search._search_duckduckgo")
    def test_routes_duckduckgo(self, mock_ddg):
        """search_api=duckduckgo 时走 _search_duckduckgo。"""
        mock_ddg.return_value = [
            {"title": "DDG", "url": "https://d.com", "content": "内容"}
        ]
        config = Configuration(search_api=SearchAPI.DUCKDUCKGO)

        payload, notices, answer, backend = dispatch_search("查询", config, 0)

        assert backend == "duckduckgo"
        assert len(payload["results"]) == 1
        mock_ddg.assert_called_once()

    @patch("services.web_search._search_local")
    def test_routes_local(self, mock_local):
        """search_api=local 时走 _search_local + 可能 baidu fallback。"""
        mock_local.return_value = [
            {"title": "本地", "url": "", "content": "本地预警数据"}
        ]
        config = Configuration(search_api=SearchAPI.LOCAL)

        payload, notices, answer, backend = dispatch_search("查询", config, 0, enterprise="测试公司")

        assert backend in ("local", "local+baidu")
        assert len(payload["results"]) >= 1
        mock_local.assert_called_once()

    @patch("services.web_search._search_tavily")
    def test_routes_tavily(self, mock_tavily):
        """search_api=tavily 时走 _search_tavily。"""
        mock_tavily.return_value = (
            [{"title": "T", "url": "https://t.com", "content": "tavily结果"}],
            "tavily answer",
        )
        config = Configuration(search_api=SearchAPI.TAVILY)

        payload, notices, answer, backend = dispatch_search("查询", config, 0)

        assert backend == "tavily"
        assert answer == "tavily answer"
        mock_tavily.assert_called_once()

    @patch("services.web_search._search_local")
    def test_unknown_api_falls_back_to_local(self, mock_local):
        """未实现的 search_api 值回退到 local。"""
        mock_local.return_value = []
        config = Configuration(search_api=SearchAPI.SEARXNG)

        payload, notices, answer, backend = dispatch_search("查询", config, 0)

        assert backend == "local"
        mock_local.assert_called_once()

    @patch("services.web_search._search_tavily")
    def test_search_exception_returns_empty(self, mock_tavily):
        """dispatch 内部异常时返回空 payload + notice。"""
        mock_tavily.side_effect = ValueError("API key missing")
        config = Configuration(search_api=SearchAPI.TAVILY)

        payload, notices, answer, backend = dispatch_search("查询", config, 0)

        assert payload["results"] == []
        assert len(notices) >= 1
        assert "搜索失败" in notices[0]
