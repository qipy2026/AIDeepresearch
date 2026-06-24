"""Web 搜索（SQLite 本地搜索为主，Tavily 可选 fallback）。"""

from __future__ import annotations

import logging
import os
import re
from typing import Any, List, Optional, Tuple

from config import Configuration
from utils import get_config_value

logger = logging.getLogger(__name__)

MAX_TOKENS_PER_SOURCE = 2000

CHINESE_STOP_WORDS = frozenset({
    "的", "了", "在", "是", "和", "与", "或", "及", "等",
    "风险", "搜索", "查询", "2026", "2025", "监控", "报告",
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

    if keywords:
        like_clauses = " OR ".join(["title LIKE ? OR detail LIKE ?"] * len(keywords))
        base_sql += f" AND ({like_clauses})"
        for kw in keywords:
            params.extend([f"%{kw}%", f"%{kw}%"])

    base_sql += """ ORDER BY CASE severity
        WHEN 'red' THEN 0 WHEN 'orange' THEN 1
        WHEN 'yellow' THEN 2 ELSE 3 END,
        created_at DESC LIMIT ?"""
    params.append(max_results)

    try:
        rows = conn.execute(base_sql, params).fetchall()
        for r in rows:
            results.append({
                "title": f"[{r['severity']}] {r['title']}",
                "url": r.get("source_url") or "",
                "content": (r.get("detail") or r.get("title"))[:500],
            })
    except Exception as exc:
        logger.warning("_search_local failed: %s", exc)
    return results


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
        elif search_api == "tavily":
            results, answer_text = _search_tavily(query, max_results)
            backend_label = "tavily"
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
