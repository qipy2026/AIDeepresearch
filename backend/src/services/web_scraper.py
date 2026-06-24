"""网页爬虫 — crawl4ai + 巨潮公告 + 关键词预筛。"""
from __future__ import annotations

import asyncio
import logging
import re
from datetime import datetime
from typing import Any

import requests
from crawl4ai import AsyncWebCrawler

logger = logging.getLogger(__name__)

CNINFO_SEARCH = "http://www.cninfo.com.cn/new/fulltextSearch/full"

_session = requests.Session()
_session.headers.update({
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
    "Referer": "http://www.cninfo.com.cn/",
})


def search_cninfo(keyword: str, days: int = 7, max_results: int = 10) -> list[dict[str, Any]]:
    """搜索巨潮资讯公告。"""
    from datetime import timedelta
    end = datetime.now()
    start = end - timedelta(days=days)

    params = {
        "searchkey": keyword, "sdate": start.strftime("%Y-%m-%d"),
        "edate": end.strftime("%Y-%m-%d"), "isfulltext": "false",
        "sortName": "pubdate", "sortType": "desc",
        "pageNum": 1, "pageSize": max_results,
    }
    try:
        resp = _session.get(CNINFO_SEARCH, params=params, timeout=15)
        resp.raise_for_status()
        data = resp.json()
        announcements = data.get("announcements") or []
        results = []
        for a in announcements:
            title = re.sub(r"<[^>]+>", "", a.get("announcementTitle", ""))
            ts = a.get("announcementTime", 0)
            dt = datetime.fromtimestamp(ts / 1000).isoformat() if ts else ""
            results.append({
                "id": a.get("announcementId", ""),
                "title": title, "time": dt,
                "sec_name": a.get("secName", ""),
                "adjunct_url": a.get("adjunctUrl", ""),
            })
        return results
    except Exception as e:
        logger.warning("cninfo search failed for '%s': %s", keyword, e)
        return []


async def _crawl_url(url: str) -> str:
    """用 crawl4ai 抓取网页并提取 markdown 文本。"""
    try:
        async with AsyncWebCrawler(verbose=False) as crawler:
            result = await crawler.arun(url=url)
            return result.markdown or ""
    except Exception as e:
        logger.warning("crawl4ai failed for %s: %s", url, e)
        return ""


def fetch_page_text(url: str) -> str:
    """同步包装：抓取网页文本。"""
    try:
        return asyncio.run(_crawl_url(url))
    except Exception as e:
        logger.warning("fetch_page_text failed: %s", e)
        return ""


# 可扩展的数据源配置
SOURCES = {
    "cninfo": {
        "name": "巨潮资讯",
        "type": "api",
    },
    "eastmoney_news": {
        "name": "东方财富新闻",
        "type": "api",
    },
    "gov_bid": {
        "name": "政府招标公告",
        "type": "baidu",
    },
    "stats_gov": {
        "name": "国家统计局",
        "type": "api",
    },
}


def collect_for_enterprise(enterprise: dict[str, Any]) -> list[dict[str, Any]]:
    """对单个企业采集公开信息。"""
    stock = enterprise.get("parent_stock_code", "") or enterprise.get("stock_code", "")
    if not stock:
        return []

    keyword = enterprise.get("parent", "") or enterprise["name"]
    keywords_config = enterprise.get("keywords", [])
    results = []

    # 巨潮公告
    announcements = search_cninfo(keyword, days=7, max_results=10)
    for a in announcements:
        title = a["title"]
        if keywords_config and not any(kw in title for kw in keywords_config):
            continue

        # 尝试抓取详情页全文
        detail_url = f"http://www.cninfo.com.cn/new/disclosure/detail?announcementId={a['id']}"
        detail = fetch_page_text(detail_url)

        text = detail[:3000] if detail else f"公司：{a['sec_name']}\n标题：{title}\n日期：{a['time'][:10]}"
        results.append({
            "title": title,
            "time": a["time"],
            "text": text,
            "source_label": f"{keyword}（巨潮公告）",
            "source": "cninfo",
            "source_url": detail_url,
        })

    return results


def load_enabled_sources() -> list[dict[str, Any]]:
    """读取 sources.yaml 中已启用的数据源。"""
    try:
        import yaml
        from pathlib import Path
        config_path = Path(__file__).resolve().parent.parent.parent / "config" / "sources.yaml"
        with open(config_path, "r", encoding="utf-8") as f:
            data = yaml.safe_load(f)
        return [s for s in data.get("sources", []) if s.get("enabled")]
    except Exception as e:
        logger.warning("Failed to load sources.yaml: %s", e)
        return []


def collect_from_sources(enterprise: dict[str, Any]) -> list[dict[str, Any]]:
    """对所有已启用的通用数据源进行采集。"""
    sources = load_enabled_sources()
    sources = [s for s in sources if not s.get("builtin")]
    if not sources:
        return []

    keyword = enterprise.get("parent", "") or enterprise["name"]
    results = []
    attempted = 0
    succeeded = 0

    for src in sources:
        attempted += 1
        try:
            text = fetch_page_text(src["url"])
            if not text or len(text) < 50:
                continue
            succeeded += 1
            results.append({
                "title": f'{src["name"]} - 数据采集',
                "time": datetime.now().isoformat(),
                "text": text[:3000],
                "source_label": f'{keyword}（{src["name"]}）',
                "source": "web_scrape",
                "source_url": src["url"],
            })
        except Exception as e:
            logger.warning("Source %s crawl failed: %s", src["name"], e)

    if attempted > 0:
        logger.info("collect_from_sources(%s): %d/%d sources returned data",
                     keyword, succeeded, attempted)
    return results


# ── Phase 3: 定向采集器 ──────────────────────────────────────────

def search_eastmoney_news(keyword: str, max_results: int = 5) -> list[dict[str, Any]]:
    """东方财富新闻搜索。通过 searchapi.eastmoney.com 按企业名搜索。"""
    try:
        url = "https://searchapi.eastmoney.com/bussiness/Web/GetCMSSearchResult"
        params = {
            "keyword": keyword,
            "type": "8197",
            "pageIndex": 1,
            "pageSize": max_results,
        }
        resp = requests.get(url, params=params, headers={
            "User-Agent": "Mozilla/5.0",
            "Referer": "https://www.eastmoney.com/",
        }, timeout=15)
        resp.raise_for_status()
        data = resp.json()
        results = []
        for item in data.get("Data", []) or []:
            title = item.get("Title", "")
            content = item.get("Content", "")
            pub_date = item.get("ShowDate", "")
            article_url = item.get("Url", "")
            if title:
                results.append({
                    "title": title,
                    "url": article_url,
                    "content": (content or title)[:500],
                    "time": pub_date,
                })
        logger.info("eastmoney_news(%s): %d results", keyword, len(results))
        return results[:max_results]
    except Exception as e:
        logger.warning("eastmoney_news(%s) failed: %s", keyword, e)
        return []


def search_gov_bid(enterprise_name: str, max_results: int = 5) -> list[dict[str, Any]]:
    """政府招标公告搜索。用百度 site:ccgp.gov.cn 限定政府采购网。"""
    try:
        from services.web_search import _search_baidu
        queries = [
            f"{enterprise_name} 中标 site:ccgp.gov.cn",
            f"{enterprise_name} 招标 公告",
        ]
        results = []
        for q in queries:
            try:
                for r in _search_baidu(q, max_results=max_results):
                    results.append({
                        "title": r.get("title", ""),
                        "url": r.get("url", ""),
                        "content": r.get("content", "")[:500],
                        "time": "",
                    })
            except Exception:
                pass
        logger.info("gov_bid(%s): %d results", enterprise_name, len(results))
        return results[:max_results]
    except Exception as e:
        logger.warning("gov_bid(%s) failed: %s", enterprise_name, e)
        return []


def fetch_stats_gov_data(indicator_codes: list[str] | None = None,
                         max_results: int = 5) -> list[dict[str, Any]]:
    """国家统计局公开数据。通过 data.stats.gov.cn API 查询宏观经济指标。"""
    if indicator_codes is None:
        indicator_codes = ["A010101", "A020101", "A050101"]
    try:
        results = []
        for code in indicator_codes[:max_results]:
            url = "https://data.stats.gov.cn/easyquery.htm"
            params = {
                "m": "QueryData",
                "dbcode": "hgnd",
                "rowcode": "zb",
                "colcode": "sj",
                "wds": "[]",
                "dfwds": f'[{{"wdcode":"zb","valuecode":"{code}"}}]',
            }
            resp = requests.get(url, params=params, timeout=15)
            resp.raise_for_status()
            data = resp.json()
            rows = (data.get("returndata") or {}).get("datanodes") or []
            for node in rows[:3]:
                wds = node.get("wds", [])
                label = next((w["wdsname"] for w in wds if w["wdcode"] == "zb"), code)
                val = node.get("data", {}).get("strdata", "N/A")
                results.append({
                    "title": f"国家统计局: {label} = {val}",
                    "url": f"https://data.stats.gov.cn/easyquery.htm?cn=A01&zb={code}",
                    "content": f"{label}: {val}",
                    "time": "",
                })
        logger.info("stats_gov: %d indicators fetched", len(results))
        return results
    except Exception as e:
        logger.warning("stats_gov failed: %s", e)
        return []


# ── Phase 4: 行业报告深层抓取 + LLM 摘要 ─────────────────────

# 咨询/研究机构站点列表（用于 site: 限定搜索）
_DEEP_REPORT_SITES = [
    "mckinsey.com.cn",
    "home.kpmg/cn",
    "bain.cn",
    "ey.com/zh_cn",
    "pwccn.com/zh",
    "deloitte.com/cn",
    "aliresearch.com",
    "tisi.org",
    "analysys.cn",
]


def search_deep_industry_reports(
    industry: str, enterprise_names: list[str],
    max_reports: int = 3,
) -> list[dict[str, Any]]:
    """行业报告深层抓取。

    对每个咨询机构站点，用百度搜索行业报告，crawl4ai 抓取全文，
    LLM 提取摘要。返回结构化结果列表。
    """
    if not industry:
        return []

    results = []
    searched = 0

    for site in _DEEP_REPORT_SITES:
        if searched >= max_reports:
            break
        try:
            from services.web_search import _search_baidu
            query = f"{industry} 研究报告 site:{site}"
            search_results = _search_baidu(query, max_results=2)
            for sr in search_results:
                if searched >= max_reports:
                    break
                url = sr.get("url", "")
                if not url:
                    continue
                # crawl4ai 抓取全文
                full_text = fetch_page_text(url)
                if not full_text or len(full_text) < 200:
                    continue
                searched += 1
                results.append({
                    "title": sr.get("title", f"{industry} 行业报告"),
                    "url": url,
                    "content": full_text[:5000],
                    "time": "",
                    "source_site": site,
                })
        except Exception as e:
            logger.warning("deep_report(%s, %s) failed: %s", industry, site, e)

    logger.info("deep_industry_reports(%s): %d reports from %d sites searched",
                industry, len(results), searched)
    return results


def _summarize_report_with_llm(text: str, enterprise_names: list[str],
                               industry: str) -> str:
    """用 LLM 提取行业报告中对监管企业相关的 3 句话摘要。"""
    try:
        from services.llm_extractor import extract_and_classify
        enterprises = [{"name": n, "role": ""} for n in enterprise_names]
        result = extract_and_classify(
            f"行业: {industry}\n\n报告内容:\n{text[:3000]}",
            enterprises,
        )
        if result.get("irrelevant"):
            return ""
        summaries = []
        for rel in result.get("relevant_enterprises", [])[:2]:
            direction = rel.get("direction", "")
            summary = rel.get("summary", "")
            if summary:
                summaries.append(f"[{direction}] {summary}")
        return "; ".join(summaries) if summaries else ""
    except Exception as e:
        logger.warning("deep_report LLM summary failed: %s", e)
        return text[:300] if text else ""
