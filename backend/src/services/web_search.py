"""Web 搜索（LangChain 生态 / 直连 API，替代 HelloAgents SearchTool）。"""

from __future__ import annotations

import logging
import os
from typing import Any, List, Optional, Tuple

from config import Configuration
from utils import get_config_value

logger = logging.getLogger(__name__)

MAX_TOKENS_PER_SOURCE = 2000

# 搜索域名黑名单 — 命中域名的搜索结果会被静默过滤
SEARCH_DOMAIN_BLOCKLIST = [
    "linkedin.com/jobs",    # LinkedIn 职位页 — 搜索误匹配
    "ye998.com",            # 色情/垃圾站
    "moneyminors.com",      # 无关内容
    "earlybird.com",        # VC网站，非企业信息
    "qs.com",               # QS教育排名，与贷后无关
    "libguides.luc.edu",    # 大学图书馆，无关
]


def _is_blocked(url: str) -> bool:
    """检查 URL 是否命中黑名单域名。"""
    if not url:
        return False
    url_lower = url.lower()
    for domain in SEARCH_DOMAIN_BLOCKLIST:
        if domain in url_lower:
            logger.info("search: blocked URL containing %s: %s", domain, url[:80])
            return True
    return False


def _search_duckduckgo(query: str, max_results: int) -> List[dict]:
    try:
        from ddgs import DDGS

        proxy = os.getenv("DDGS_PROXY", "")
        ddgs_kwargs = {}
        if proxy:
            ddgs_kwargs["proxy"] = proxy
        rows = DDGS(**ddgs_kwargs).text(query, max_results=max_results)
        results = []
        for r in rows or []:
            results.append(
                {
                    "title": r.get("title") or "",
                    "url": r.get("href") or r.get("url") or "",
                    "content": r.get("body") or r.get("snippet") or "",
                }
            )
        return results
    except Exception as exc:
        logger.warning("DuckDuckGo search failed: %s", exc)
        raise


def _search_tavily(query: str, max_results: int) -> Tuple[List[dict], Optional[str]]:
    key = os.getenv("TAVILY_API_KEY")
    if not key:
        raise ValueError("TAVILY_API_KEY 未配置")
    from tavily import TavilyClient

    client = TavilyClient(api_key=key)
    resp = client.search(query=query, max_results=max_results)
    results = []
    for item in resp.get("results") or []:
        results.append(
            {
                "title": item.get("title") or "",
                "url": item.get("url") or "",
                "content": item.get("content") or "",
            }
        )
    return results, resp.get("answer")


def dispatch_search(
    query: str,
    config: Configuration,
    loop_count: int,
) -> Tuple[dict[str, Any] | None, list[str], Optional[str], str]:
    search_api = get_config_value(config.search_api)
    max_results = 5

    try:
        answer_text: Optional[str] = None
        if search_api == "tavily":
            results, answer_text = _search_tavily(query, max_results)
            backend_label = "tavily"
        else:
            results = _search_duckduckgo(query, max_results)
            backend_label = "duckduckgo"

        # 过滤黑名单域名
        filtered = []
        for r in results:
            url = r.get("url") or r.get("href") or ""
            if _is_blocked(url):
                continue
            filtered.append(r)

        payload: dict[str, Any] = {
            "results": filtered,
            "backend": backend_label,
            "answer": answer_text,
            "notices": [],
        }
        return payload, [], answer_text, backend_label
    except Exception as exc:
        notice = f"搜索失败（{search_api}）：{exc}"
        logger.warning(notice)
        payload = {
            "results": [],
            "backend": search_api,
            "answer": None,
            "notices": [notice],
        }
        return payload, [notice], None, search_api
