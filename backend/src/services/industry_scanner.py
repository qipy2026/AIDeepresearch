"""全行业扫描——东方财富行业板块 + 交叉匹配。"""
from __future__ import annotations

import logging
from datetime import datetime
from typing import Any

import requests

logger = logging.getLogger(__name__)

EASTMONEY_API = "http://push2.eastmoney.com/api/qt/clist/get"

_cache: dict[str, Any] | None = None
_cache_time: datetime | None = None


def _get(url: str) -> dict | None:
    try:
        r = requests.get(url, headers={
            "User-Agent": "Mozilla/5.0",
            "Referer": "http://quote.eastmoney.com/",
        }, timeout=10)
        r.raise_for_status()
        return r.json()
    except Exception as e:
        logger.warning("EastMoney fetch failed: %s", e)
        return None


def fetch_eastmoney_sectors(sector_type: str = "industry",
                            sort: str = "gainers",
                            top_n: int = 10) -> list[dict[str, Any]]:
    fs = "m:90+t:2" if sector_type == "industry" else "m:90+t:3"
    po = 1 if sort == "gainers" else 0
    url = (f"{EASTMONEY_API}?pn=1&pz={top_n}&po={po}&np=1"
           f"&ut=bd1d9ddb04089700cf9c27f6f7426281&fltt=2&invt=2"
           f"&fid=f3&fs={fs}"
           f"&fields=f2,f3,f4,f12,f14,f20,f104,f105,f128,f140")

    data = _get(url)
    if not data or not data.get("data") or not data["data"].get("diff"):
        return []

    return [
        {
            "code": i.get("f12", ""),
            "name": i.get("f14", ""),
            "change_pct": round(float(i.get("f3", 0)), 2),
            "index_value": float(i.get("f2", 0)),
            "market_cap": float(i.get("f20", 0)),
            "up_count": int(i.get("f104", 0)),
            "down_count": int(i.get("f105", 0)),
            "lead_stock": i.get("f128", ""),
        }
        for i in data["data"]["diff"]
    ]


def _fuzzy_match(name: str, industry: str, sector: str) -> bool:
    for s in [name.lower(), industry.lower()]:
        if not s:
            continue
        if s in sector.lower() or sector.lower() in s:
            return True
        for i in range(len(s) - 1):
            if s[i:i + 2] in sector.lower():
                return True
    return False


def scan_and_match(enterprises: list[dict[str, Any]],
                   ths_user: str = "", ths_pass: str = "") -> dict[str, Any]:
    global _cache, _cache_time
    now = datetime.now()
    if _cache and _cache_time and (now - _cache_time).seconds < 600:
        return _cache

    sectors = (
        fetch_eastmoney_sectors("industry", "gainers", 20) +
        fetch_eastmoney_sectors("industry", "losers", 20) +
        fetch_eastmoney_sectors("concept", "gainers", 20) +
        fetch_eastmoney_sectors("concept", "losers", 20)
    )

    seen = set()
    unique = []
    for s in sectors:
        if s["code"] not in seen:
            seen.add(s["code"])
            unique.append(s)

    top_gainers = sorted(
        [s for s in unique if s["change_pct"] > 0],
        key=lambda x: -x["change_pct"]
    )[:10]
    top_losers = sorted(
        [s for s in unique if s["change_pct"] < 0],
        key=lambda x: x["change_pct"]
    )[:10]

    parties = [e for e in enterprises if e.get("role") == "甲方"]
    matched_risks = []
    matched_opportunities = []

    for p in parties:
        name = p.get("name", "")
        industry = p.get("industry", "")

        for s in top_losers:
            if _fuzzy_match(name, industry, s["name"]):
                chg = s["change_pct"]
                matched_risks.append({
                    "enterprise": name, "sector": s["name"],
                    "sector_code": s["code"],
                    "change_pct": chg,
                    "lead_stock": s["lead_stock"],
                    "level": "red" if chg <= -5 else ("orange" if chg <= -2 else "yellow"),
                })

        for s in top_gainers:
            if _fuzzy_match(name, industry, s["name"]):
                matched_opportunities.append({
                    "enterprise": name, "sector": s["name"],
                    "sector_code": s["code"],
                    "change_pct": s["change_pct"],
                    "covered": True,
                })

    covered = {m["sector_code"] for m in matched_opportunities}
    missed = [
        {"sector": s["name"], "sector_code": s["code"],
         "change_pct": s["change_pct"], "lead_stock": s["lead_stock"]}
        for s in top_gainers if s["change_pct"] >= 3 and s["code"] not in covered
    ]

    result = {
        "top_gainers": top_gainers, "top_losers": top_losers,
        "matched_risks": matched_risks,
        "matched_opportunities": matched_opportunities,
        "missed_opportunities": missed,
        "updated_at": now.isoformat(),
    }
    _cache = result
    _cache_time = now
    return result
