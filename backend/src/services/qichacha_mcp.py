"""企查查 MCP 客户端封装（SSE 流式 JSON-RPC）。"""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any, Optional

import requests
from dotenv import load_dotenv

# Ensure .env is loaded before reading token
_backend_root = Path(__file__).resolve().parent.parent.parent
load_dotenv(_backend_root / ".env", override=True)

_QCC_TOKEN = os.getenv("QICHACHA_MCP_TOKEN", "")

# MCP 服务配置
MCP_CONFIG: dict[str, dict[str, str]] = {
    "company": {"url": "https://agent.qcc.com/mcp/company/stream", "token": _QCC_TOKEN},
    "risk": {"url": "https://agent.qcc.com/mcp/risk/stream", "token": _QCC_TOKEN},
    "operation": {"url": "https://agent.qcc.com/mcp/operation/stream", "token": _QCC_TOKEN},
    "executive": {"url": "https://agent.qcc.com/mcp/executive/stream", "token": _QCC_TOKEN},
    "ipr": {"url": "https://agent.qcc.com/mcp/ipr/stream", "token": _QCC_TOKEN},
    "history": {"url": "https://agent.qcc.com/mcp/history/stream", "token": _QCC_TOKEN},
}

_request_id = 0


def call_tool(service: str, tool: str, args: dict[str, Any]) -> Optional[dict[str, Any]]:
    """调用企查查 MCP 工具，返回解析后的完整 result dict。"""
    global _request_id
    cfg = MCP_CONFIG.get(service)
    if not cfg:
        return None

    _request_id += 1
    body = {
        "jsonrpc": "2.0",
        "id": _request_id,
        "method": "tools/call",
        "params": {"name": tool, "arguments": args},
    }

    try:
        r = requests.post(
            cfg["url"],
            json=body,
            headers={
                "Authorization": f"Bearer {cfg['token']}",
                "Content-Type": "application/json",
            },
            stream=True,
            timeout=20,
        )
        for line in r.iter_lines():
            if not line:
                continue
            raw = line.decode("utf-8", errors="replace")
            if raw.startswith("data: "):
                try:
                    d = json.loads(raw[6:])
                    result = d.get("result")
                    if result and "content" in result:
                        return result
                except json.JSONDecodeError:
                    continue
            # 检查 error
            if raw.startswith("data: ") and '"error"' in raw:
                try:
                    d = json.loads(raw[6:])
                    err = d.get("error", {})
                    if err.get("code"):
                        return None
                except json.JSONDecodeError:
                    continue
    except Exception:
        return None
    return None


def _extract_text(result: dict) -> str:
    """从 MCP result 中提取文本内容。"""
    parts: list[str] = []
    for item in result.get("content", []):
        if isinstance(item, dict):
            text = item.get("text", "")
            if text:
                parts.append(text)
    return "\n".join(parts)


# ── 便捷函数 ──────────────────────────────────────────────

def query_company_profile(keyword: str) -> Optional[str]:
    """查询企业概况（经营状态、行业、法人等）。"""
    r = call_tool("company", "get_company_profile", {"keyword": keyword})
    return _extract_text(r) if r else None


def query_company_registration(keyword: str) -> Optional[str]:
    """查询工商注册信息。"""
    r = call_tool("company", "get_company_registration_info", {"keyword": keyword})
    return _extract_text(r) if r else None


def query_risk_scan(keyword: str) -> Optional[str]:
    """企业风险扫描概览。"""
    r = call_tool("risk", "get_company_risk_scan", {"searchKey": keyword})
    return _extract_text(r) if r else None


def query_administrative_penalty(keyword: str) -> Optional[str]:
    """行政处罚记录。"""
    r = call_tool("risk", "get_administrative_penalty", {"searchKey": keyword})
    return _extract_text(r) if r else None


def query_judicial_documents(keyword: str) -> Optional[str]:
    """法律诉讼/裁判文书。"""
    r = call_tool("risk", "get_judicial_documents", {"searchKey": keyword})
    return _extract_text(r) if r else None


def query_dishonest(keyword: str) -> Optional[str]:
    """失信信息（债务违约）。"""
    r = call_tool("risk", "get_dishonest_info", {"searchKey": keyword})
    return _extract_text(r) if r else None


def query_bidding(keyword: str) -> Optional[str]:
    """招投标信息。"""
    r = call_tool("operation", "get_bidding_info", {"searchKey": keyword})
    return _extract_text(r) if r else None


def query_news(keyword: str) -> Optional[str]:
    """新闻舆情。"""
    r = call_tool("operation", "get_news_sentiment", {"searchKey": keyword})
    return _extract_text(r) if r else None


def query_key_personnel(keyword: str) -> Optional[str]:
    """高管信息。"""
    r = call_tool("company", "get_key_personnel", {"keyword": keyword})
    return _extract_text(r) if r else None


def query_recruitment(keyword: str) -> Optional[str]:
    """招聘信息。"""
    r = call_tool("operation", "get_recruitment_info", {"searchKey": keyword})
    return _extract_text(r) if r else None


def query_qualifications(keyword: str) -> Optional[str]:
    """资质证书。"""
    r = call_tool("operation", "get_qualifications", {"searchKey": keyword})
    return _extract_text(r) if r else None
