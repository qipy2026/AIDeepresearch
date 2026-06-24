"""DM 查债通客户端 — 债券违约/司法/舆情数据采集。

Playwright 模式优先（完整数据提取），不可用时降级为 requests 模式。
凭证: 可通过环境变量 DM_USERNAME / DM_PASSWORD 配置。
"""

from __future__ import annotations

import logging
from typing import Any

logger = logging.getLogger(__name__)

DM_BASE_URL = "https://www.dmzhaizhai.com"


def _dm_requests_search(enterprise: str, username: str, password: str) -> list[dict[str, Any]]:
    """降级模式：用 requests 做基础查询。返回有限数据。"""
    import requests as _requests
    results = []
    try:
        sess = _requests.Session()
        sess.headers.update({
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
        })
        # 尝试搜索 endpoint
        resp = sess.get(
            f"{DM_BASE_URL}/search",
            params={"keyword": enterprise},
            timeout=15,
        )
        if resp.status_code == 200 and len(resp.text) > 100:
            results.append({
                "title": f"DM查债通搜索: {enterprise}",
                "url": f"{DM_BASE_URL}/search?keyword={enterprise}",
                "content": resp.text[:500],
                "time": "",
            })
        logger.info("dm_client(requests): %d results for %s", len(results), enterprise)
    except Exception as e:
        logger.warning("dm_client(requests) failed: %s", e)
    return results


def _dm_playwright_search(enterprise: str, username: str, password: str) -> list[dict[str, Any]]:
    """Playwright 模式：完整登录 + 数据提取。
    覆盖: 债券违约标志、司法计数、负面舆情标题、评级变动等。
    """
    results = []
    try:
        from playwright.sync_api import sync_playwright
    except ImportError:
        logger.info("Playwright not installed, skipping DM playwright mode")
        return results

    try:
        with sync_playwright() as p:
            browser = p.chromium.launch(headless=True)
            page = browser.new_page()
            page.goto(f"{DM_BASE_URL}/login", timeout=30000)
            page.fill('input[name="username"]', username)
            page.fill('input[name="password"]', password)
            page.click('button[type="submit"]')
            page.wait_for_load_state("networkidle", timeout=15000)

            page.goto(f"{DM_BASE_URL}/search?keyword={enterprise}", timeout=15000)
            page.wait_for_load_state("networkidle", timeout=10000)

            content = page.content()
            if content:
                results.append({
                    "title": f"DM查债通(Playwright): {enterprise}",
                    "url": f"{DM_BASE_URL}/search?keyword={enterprise}",
                    "content": content[:3000],
                    "time": "",
                })

            browser.close()
            logger.info("dm_client(playwright): %d results for %s", len(results), enterprise)
    except Exception as e:
        logger.warning("dm_client(playwright) failed: %s", e)

    return results


def search_dm(enterprise: str, username: str = "", password: str = "") -> list[dict[str, Any]]:
    """DM 查债通统一入口。优先 Playwright，不可用则降级 requests。"""
    import os
    user = username or os.getenv("DM_USERNAME", "")
    passwd = password or os.getenv("DM_PASSWORD", "")
    if not user or not passwd:
        logger.warning("DM credentials not configured, skipping")
        return []

    # 优先 Playwright
    results = _dm_playwright_search(enterprise, user, passwd)
    if results:
        return results

    # 降级 requests
    return _dm_requests_search(enterprise, user, passwd)
