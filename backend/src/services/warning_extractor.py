"""Extractor — 解析各数据源响应，提取人类可读信息。"""
from __future__ import annotations

import json
from typing import Any, Dict, Optional, Tuple


def extract(source: str, raw_text: str) -> Dict[str, str]:
    """根据数据源类型解析 raw_text 为结构化的可读字符串。

    Returns:
        {"summary": 摘要, "readable": 可读全文, "key_facts": 关键事实列表}
    """
    if source == "qichacha":
        return _extract_qichacha(raw_text)
    if source == "piaojiaosuo":
        return _extract_rag_text(raw_text)
    return _extract_fallback(raw_text)


def _extract_qichacha(text: str) -> Dict[str, str]:
    """解析企查查 JSON 响应。"""
    try:
        data = json.loads(text)
    except (json.JSONDecodeError, TypeError):
        return _extract_fallback(text)

    enterprise = data.get("企业名称", "")
    abstract = data.get("摘要", "")
    record_factors = data.get("有记录因子数", 0)
    total_factors = record_factors + data.get("无记录因子数", 0)
    scans = data.get("风险因子扫描", [])

    # 提取有记录的风险因子
    active = []
    for item in scans:
        count = item.get("条目数", 0)
        if count > 0:
            active.append(f"{item.get('风险因子', '')}({count})")

    summary = f"{enterprise}: {abstract}" if enterprise else abstract
    readable = (
        f"企业: {enterprise}\n"
        f"风险扫描: {record_factors}/{total_factors} 项有记录\n"
    )
    if active:
        readable += f"明细: {', '.join(active)}"
    else:
        readable += "未发现重大风险信号"

    return {
        "summary": summary,
        "readable": readable,
        "title": f"{enterprise} 风险扫描" if enterprise else "企查查风险扫描",
        "abstract": abstract,
        "key_facts": ", ".join(active) if active else "无异常",
    }


def _extract_rag_text(text: str) -> Dict[str, str]:
    """解析 RAG/票交所检索文本。"""
    clean = text.strip()
    # ChromaDB 返回的文档片段
    lines = [l.strip() for l in clean.split("\n") if l.strip()]
    readable = "\n".join(lines[:20])
    return {
        "summary": lines[0] if lines else clean[:200],
        "readable": readable[:2000],
        "title": "票交所商票信息",
        "abstract": readable[:500],
        "key_facts": "",
    }


def _extract_fallback(text: str) -> Dict[str, str]:
    """通用文本提取。"""
    clean = text.strip()
    return {
        "summary": clean[:200],
        "readable": clean[:1000],
        "title": clean[:100],
        "abstract": clean[:500],
        "key_facts": "",
    }
