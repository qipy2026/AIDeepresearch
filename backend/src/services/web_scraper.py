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
        "type": "api",  # 用 API 搜索 + crawl4ai 抓详情
    },
    # 后续扩展:
    # "eastmoney_news": {"name": "东方财富新闻", "type": "crawl"},
    # "gov_bid": {"name": "政府招标公告", "type": "crawl"},
    # "stats_gov": {"name": "国家统计局", "type": "crawl"},
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

    for src in sources:
        try:
            text = fetch_page_text(src["url"])
            if not text or len(text) < 50:
                continue
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

    return results
