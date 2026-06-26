"""Web 搜索（SQLite 本地搜索为主，Tavily 可选 fallback）。"""

from __future__ import annotations

import logging
import os
import re
from typing import Any, List, Optional, Tuple

import requests

from config import Configuration
from utils import get_config_value

logger = logging.getLogger(__name__)

MAX_TOKENS_PER_SOURCE = 2000

CHINESE_STOP_WORDS = frozenset({
    "的", "了", "在", "是", "和", "与", "或", "及", "等", "与",
    "搜索", "查询", "2026", "2025", "监控", "报告", "OR",
})


def _extract_keywords(query: str) -> List[str]:
    """从搜索 query 中提取中文关键词。"""
    tokens = re.split(r"[\s,，、]+", query)
    return [t.strip() for t in tokens if len(t.strip()) >= 2 and t.strip() not in CHINESE_STOP_WORDS]


def _search_local(
    query: str, enterprise: str = "", max_results: int = 5
) -> List[dict]:
    """从 SQLite warning_log 表中搜索预警数据。"""
    from warning_db import WarningDB
    db = WarningDB()
    keywords = _extract_keywords(query)
    conn = db._get_conn()
    results: List[dict] = []

    # 企业名精确匹配优先
    base_sql = """SELECT title, detail, severity, source, source_url, created_at
                  FROM warning_log WHERE 1=1"""
    params: list = []

    if enterprise:
        base_sql += " AND enterprise LIKE ?"
        params.append(f"%{enterprise}%")

    def _execute(extra_clause: str, extra_params: list) -> List[dict]:
        sql = base_sql + extra_clause
        sql += """ ORDER BY CASE severity
            WHEN 'red' THEN 0 WHEN 'orange' THEN 1
            WHEN 'yellow' THEN 2 ELSE 3 END,
            created_at DESC LIMIT ?"""
        all_params = params + extra_params + [max_results]
        rows = conn.execute(sql, all_params).fetchall()
        out = []
        for r in rows:
            d = dict(r)
            out.append({
                "title": f"[{d['severity']}] {d['title']}",
                "url": d.get("source_url") or "",
                "content": (d.get("detail") or d.get("title"))[:500],
            })
        return out

    try:
        if keywords:
            like_clauses = " OR ".join(["title LIKE ? OR detail LIKE ?"] * len(keywords))
            kw_params = []
            for kw in keywords:
                kw_params.extend([f"%{kw}%", f"%{kw}%"])
            results = _execute(f" AND ({like_clauses})", kw_params)

        # Fallback: keyword match 无结果时返回企业全部预警（按 severity 排序）
        if not results:
            results = _execute("", [])
    except Exception as exc:
        logger.warning("_search_local failed: %s", exc)
    return results


def _search_duckduckgo(query: str, max_results: int = 5) -> List[dict]:
    """DuckDuckGo 搜索。使用 ddgs 库（已在 pyproject.toml 依赖中）。"""
    try:
        from ddgs import DDGS
        results = []
        with DDGS() as ddgs:
            for r in ddgs.text(query, max_results=max_results):
                results.append({
                    "title": r.get("title", ""),
                    "url": r.get("href", ""),
                    "content": r.get("body", ""),
                })
        return results
    except Exception as exc:
        logger.warning("DuckDuckGo搜索失败: %s", exc)
        return []


def _search_baidu(query: str, max_results: int = 5) -> List[dict]:
    """百度千帆 AI 搜索。需要 BAIDU_ACCESS_TOKEN 环境变量。"""
    token = os.getenv("BAIDU_ACCESS_TOKEN", "")
    if not token:
        logger.warning("BAIDU_ACCESS_TOKEN 未配置，百度搜索不可用")
        return []
    try:
        resp = requests.post(
            "https://qianfan.baidubce.com/v2/ai_search",
            headers={
                "Authorization": f"Bearer {token}",
                "Content-Type": "application/json",
            },
            json={
                "messages": [{"content": query, "role": "user"}],
                "search_source": "baidu_search_v2",
            },
            timeout=30,
        )
        resp.raise_for_status()
        data = resp.json()
        results = []
        for r in (data.get("search_results") or [])[:max_results]:
            results.append({
                "title": r.get("title", ""),
                "url": r.get("url", ""),
                "content": r.get("abstract") or r.get("content", ""),
            })
        return results
    except Exception as exc:
        logger.warning("百度搜索失败: %s", exc)
        return []


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
    enterprise: str = "",
) -> Tuple[dict[str, Any] | None, list[str], Optional[str], str]:
    search_api = get_config_value(config.search_api)
    max_results = 5

    try:
        answer_text: Optional[str] = None
        if search_api == "local":
            results = _search_local(query, enterprise=enterprise, max_results=max_results)
            backend_label = "local"
            # 本地数据不足时自动 fallback 百度搜索
            if len(results) < 3:
                baidu_results = _search_baidu(query, max_results=max_results - len(results))
                if baidu_results:
                    results = results + baidu_results
                    backend_label = "local+baidu"
        elif search_api == "baidu":
            results = _search_baidu(query, max_results=max_results)
            backend_label = "baidu"
        elif search_api == "tavily":
            results, answer_text = _search_tavily(query, max_results)
            backend_label = "tavily"
        elif search_api == "duckduckgo":
            results = _search_duckduckgo(query, max_results=max_results)
            backend_label = "duckduckgo"
        else:
            # 兜底：其他后端走 local
            results = _search_local(query, enterprise=enterprise, max_results=max_results)
            backend_label = "local"

        payload: dict[str, Any] = {
            "results": results,
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
