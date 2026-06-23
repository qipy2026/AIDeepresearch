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
    """解析企查查 JSON 响应，生成用户向风险摘要。"""
    try:
        data = json.loads(text)
    except (json.JSONDecodeError, TypeError):
        return _extract_fallback(text)

    enterprise = data.get("企业名称", "")
    scans = data.get("风险因子扫描", [])

    # 分级提取：告警类（红色）和关注类（黄色）
    alert_factors = []  # 失信、被执行人、行政处罚等
    watch_factors = []  # 裁判文书、立案、开庭等
    for item in scans:
        count = item.get("条目数", 0)
        if count > 0:
            name = item.get("风险因子", "")
            if name in ("失信信息", "被执行人", "限制高消费", "行政处罚", "经营异常", "严重违法", "破产重整", "清算信息"):
                alert_factors.append(f"{name}({count})")
            else:
                watch_factors.append(f"{name}({count})")

    # 生成用户向标题: "中铁建物业成都 — 行政处罚1项、裁判文书59项"
    top_items = alert_factors + watch_factors
    title = f"{enterprise}"
    if top_items:
        title += f" — {'、'.join(top_items[:4])}"
        if len(top_items) > 4:
            title += f" 等{len(top_items)}项"

    # 生成用户向摘要：突出最严重的信号
    if alert_factors:
        summary = f"⚠️ 告警信号: {'、'.join(alert_factors)}"
    elif watch_factors:
        summary = f"📋 风险信号: {'、'.join(watch_factors[:5])}"
    else:
        summary = "未发现风险信号"

    # 可读全文（去除开发者提示语）
    abstract = data.get("摘要", "")
    # 移除企查查对开发者的提示
    abstract = abstract.replace("各因子明细请调用其「明细工具」", "").replace("。", "。").strip()
    if abstract.endswith("。"):
        abstract = abstract[:-1]

    readable = abstract if abstract else summary

    return {
        "summary": summary,
        "readable": readable,
        "title": title,
        "abstract": abstract,
        "key_facts": ", ".join(top_items) if top_items else "无异常",
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
