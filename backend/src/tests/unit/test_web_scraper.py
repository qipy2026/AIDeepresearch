"""Unit tests for web_scraper — cninfo, crawl4ai, collectors.

Covers: search_cninfo, fetch_page_text, collect_for_enterprise,
        load_enabled_sources, collect_from_sources, search_eastmoney_news,
        search_gov_bid, fetch_stats_gov_data, search_deep_industry_reports.
"""

import json
from unittest.mock import patch, MagicMock

import pytest
from services.web_scraper import (
    search_cninfo,
    fetch_page_text,
    collect_for_enterprise,
    load_enabled_sources,
    collect_from_sources,
    search_eastmoney_news,
    search_gov_bid,
    fetch_stats_gov_data,
    search_deep_industry_reports,
    SOURCES,
)


# ── search_cninfo ────────────────────────────────────────────────

class TestSearchCninfo:
    """巨潮资讯公告搜索。"""

    def test_successful_search_returns_parsed_results(self):
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = {
            "announcements": [
                {
                    "announcementId": "1001",
                    "announcementTitle": "<em>风险</em>提示公告",
                    "announcementTime": 1700000000000,
                    "secName": "测试公司",
                    "adjunctUrl": "http://example.com/pdf",
                }
            ]
        }
        with patch("services.web_scraper._session.get", return_value=mock_resp):
            results = search_cninfo("风险", days=7, max_results=5)
            assert len(results) == 1
            assert results[0]["id"] == "1001"
            assert "风险提示公告" in results[0]["title"]
            assert results[0]["sec_name"] == "测试公司"

    def test_empty_announcements_returns_empty_list(self):
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = {"announcements": []}
        with patch("services.web_scraper._session.get", return_value=mock_resp):
            assert search_cninfo("不存在的关键词") == []

    def test_http_error_returns_empty_list(self):
        with patch("services.web_scraper._session.get", side_effect=Exception("timeout")):
            assert search_cninfo("测试") == []

    def test_no_announcements_key_returns_empty(self):
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = {}
        with patch("services.web_scraper._session.get", return_value=mock_resp):
            assert search_cninfo("test") == []


# ── fetch_page_text ──────────────────────────────────────────────

class TestFetchPageText:
    """crawl4ai 同步包装器。"""

    def test_successful_fetch_returns_markdown(self):
        async def _mock_crawl(url):
            result = MagicMock()
            result.markdown = "# Page content"
            return result

        with patch("services.web_scraper._crawl_url", side_effect=_mock_crawl):
            text = fetch_page_text("http://example.com")
            assert text == "# Page content"

    def test_fetch_exception_returns_empty(self):
        async def _mock_crawl(url):
            raise RuntimeError("crawl broken")

        with patch("services.web_scraper._crawl_url", side_effect=_mock_crawl):
            text = fetch_page_text("http://bad.com")
            assert text == ""


# ── collect_for_enterprise ───────────────────────────────────────

class TestCollectForEnterprise:
    """企业信息采集主函数。"""

    def test_no_stock_code_returns_empty(self):
        enterprise = {"name": "测试企业"}
        assert collect_for_enterprise(enterprise) == []

    def test_with_stock_and_keywords(self):
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = {
            "announcements": [{
                "announcementId": "2001",
                "announcementTitle": "违约风险公告",
                "announcementTime": 1700000000000,
                "secName": "测试上市公司",
                "adjunctUrl": "",
            }]
        }
        enterprise = {
            "name": "测试企业",
            "parent_stock_code": "600001",
            "keywords": ["违约"],
        }
        with patch("services.web_scraper._session.get", return_value=mock_resp), \
             patch("services.web_scraper.fetch_page_text", return_value="公告全文内容"):
            results = collect_for_enterprise(enterprise)
            assert len(results) >= 1
            assert results[0]["source"] == "cninfo"

    def test_keyword_filter_skips_irrelevant(self):
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = {
            "announcements": [{
                "announcementId": "3001",
                "announcementTitle": "定期报告",
                "announcementTime": 1700000000000,
                "secName": "测试公司",
                "adjunctUrl": "",
            }]
        }
        enterprise = {
            "name": "测试企业",
            "parent_stock_code": "600002",
            "keywords": ["风险"],
        }
        with patch("services.web_scraper._session.get", return_value=mock_resp):
            results = collect_for_enterprise(enterprise)
            # "定期报告" does not contain "风险" → filtered out
            assert len(results) == 0


# ── load_enabled_sources + collect_from_sources ──────────────────

class TestLoadEnabledSources:
    """sources.yaml 配置加载。"""

    def test_yaml_file_not_found_returns_empty(self):
        with patch("services.web_scraper.Path.exists", return_value=False):
            # load_enabled_sources catches Exception and returns []
            # If file doesn't exist, yaml.safe_load raises; but since we
            # mock open to fail, the except path runs
            with patch("builtins.open", side_effect=FileNotFoundError):
                assert load_enabled_sources() == []

    def test_enabled_filter(self):
        mock_yaml = {
            "sources": [
                {"name": "src1", "enabled": True},
                {"name": "src2", "enabled": False},
                {"name": "src3", "enabled": True},
            ]
        }
        with patch("builtins.open", MagicMock()), \
             patch("services.web_scraper.yaml.safe_load", return_value=mock_yaml), \
             patch("services.web_scraper.Path.exists", return_value=True):
            sources = load_enabled_sources()
            assert len(sources) == 2
            assert all(s["enabled"] for s in sources)


class TestCollectFromSources:
    """通用数据源采集。"""

    def test_no_enabled_sources_returns_empty(self):
        with patch("services.web_scraper.load_enabled_sources", return_value=[]):
            assert collect_from_sources({"name": "test"}) == []

    def test_filters_builtin_sources(self):
        mock_sources = [
            {"name": "custom_source", "enabled": True, "url": "http://example.com"},
            {"name": "builtin_src", "enabled": True, "builtin": True, "url": ""},
        ]
        with patch("services.web_scraper.load_enabled_sources", return_value=mock_sources), \
             patch("services.web_scraper.fetch_page_text", return_value="valid content here x" * 5):
            results = collect_from_sources({"name": "test_ent"})
            # builtin source filtered, only custom_source used
            assert len(results) == 1

    def test_short_content_skipped(self):
        mock_sources = [
            {"name": "short_src", "enabled": True, "url": "http://example.com"},
        ]
        with patch("services.web_scraper.load_enabled_sources", return_value=mock_sources), \
             patch("services.web_scraper.fetch_page_text", return_value="too short"):
            results = collect_from_sources({"name": "test"})
            assert results == []

    def test_crawl_exception_skips_source(self):
        mock_sources = [
            {"name": "failing_src", "enabled": True, "url": "http://bad.com"},
        ]
        with patch("services.web_scraper.load_enabled_sources", return_value=mock_sources), \
             patch("services.web_scraper.fetch_page_text", side_effect=Exception("fail")):
            results = collect_from_sources({"name": "test"})
            assert results == []


# ── Phase 3 collectors ───────────────────────────────────────────

class TestSearchEastmoneyNews:
    """东方财富新闻搜索。"""

    def test_successful_search(self):
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = {
            "Data": [
                {"Title": "重大利好", "Content": "详细内容", "ShowDate": "2026-06-24", "Url": "http://eastmoney.com/1"}
            ]
        }
        with patch("requests.get", return_value=mock_resp):
            results = search_eastmoney_news("测试企业")
            assert len(results) == 1
            assert results[0]["title"] == "重大利好"

    def test_http_error_returns_empty(self):
        with patch("requests.get", side_effect=Exception("network error")):
            assert search_eastmoney_news("test") == []

    def test_empty_data_returns_empty(self):
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = {"Data": []}
        with patch("requests.get", return_value=mock_resp):
            assert search_eastmoney_news("test") == []


class TestSearchGovBid:
    """政府招标公告搜索。"""

    def test_successful_baidu_results(self):
        with patch("services.web_scraper._search_baidu") as mock_baidu:
            mock_baidu.return_value = [
                {"title": "中标公告", "url": "http://ccgp.gov.cn/1", "content": "content"}
            ]
            results = search_gov_bid("测试企业")
            assert len(results) >= 1
            assert results[0]["title"] == "中标公告"

    def test_exception_returns_empty(self):
        with patch("services.web_scraper._search_baidu", side_effect=Exception("error")):
            assert search_gov_bid("test") == []

    def test_baidu_query_failure_not_fatal(self):
        """Second query fails, first still returns results."""
        call_count = [0]

        def _mock_baidu(q, max_results=3):
            call_count[0] += 1
            if call_count[0] == 1:
                return [{"title": "t1", "url": "u1", "content": "c1"}]
            raise Exception("fail")

        with patch("services.web_scraper._search_baidu", side_effect=_mock_baidu):
            results = search_gov_bid("test")
            assert len(results) == 1


class TestFetchStatsGov:
    """国家统计局数据查询。"""

    def test_successful_fetch(self):
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = {
            "returndata": {
                "datanodes": [
                    {"wds": [{"wdcode": "zb", "wdsname": "GDP"}], "data": {"strdata": "100万亿"}}
                ]
            }
        }
        with patch("requests.get", return_value=mock_resp):
            results = fetch_stats_gov_data(["A010101"])
            assert len(results) >= 1
            assert "GDP" in results[0]["title"]

    def test_error_returns_empty(self):
        with patch("requests.get", side_effect=Exception("error")):
            assert fetch_stats_gov_data() == []

    def test_default_indicators_used_when_none(self):
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = {"returndata": {"datanodes": []}}
        with patch("requests.get", return_value=mock_resp):
            results = fetch_stats_gov_data(None)
            assert results == []


# ── Phase 4 deep reports ─────────────────────────────────────────

class TestDeepIndustryReports:
    """行业报告深层抓取。"""

    def test_no_industry_returns_empty(self):
        assert search_deep_industry_reports("", ["ent1"]) == []

    def test_successful_search_with_results(self):
        with patch("services.web_scraper._search_baidu") as mock_baidu, \
             patch("services.web_scraper.fetch_page_text", return_value="report content " * 20):
            mock_baidu.return_value = [
                {"title": "行业报告2026", "url": "http://example.com/report"}
            ]
            results = search_deep_industry_reports("物业管理", ["企业A"], max_reports=1)
            assert len(results) >= 1

    def test_empty_search_results_returns_empty(self):
        with patch("services.web_scraper._search_baidu", return_value=[]):
            assert search_deep_industry_reports("物业管理", ["ent"]) == []

    def test_short_content_skipped(self):
        with patch("services.web_scraper._search_baidu") as mock_baidu, \
             patch("services.web_scraper.fetch_page_text", return_value="short"):
            mock_baidu.return_value = [{"title": "t", "url": "http://example.com"}]
            results = search_deep_industry_reports("物业管理", ["ent"])
            assert results == []

    def test_site_search_exception_not_fatal(self):
        """One site fails, others still searched."""
        with patch("services.web_scraper._search_baidu", side_effect=Exception("fail")):
            results = search_deep_industry_reports("物业管理", ["ent"])
            assert results == []
