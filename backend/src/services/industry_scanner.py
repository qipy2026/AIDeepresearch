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

    # 东方财富不通则走同花顺 SDK
    if not unique:
        return _ths_fallback(enterprises, ths_user, ths_pass, now)

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


def _ths_fallback(enterprises, ths_user, ths_pass, now) -> dict[str, Any]:
    """同花顺 SDK 兜底——东财不通时使用。"""
    try:
        from iFinDPy import THS_iFinDLogin, THS_RQ, THS_iFinDLogout
        THS_iFinDLogin(ths_user or "dhsybl002", ths_pass or "5TSc27g4")
    except Exception:
        return _empty(now)

    CODES = {
        "885692.TI": "地下管网", "885431.TI": "物业管理", "885438.TI": "建筑装饰",
        "885502.TI": "安防", "885411.TI": "煤炭", "885521.TI": "新能源",
        "885522.TI": "电力", "885519.TI": "石油石化", "885443.TI": "汽车",
        "885451.TI": "机械设备", "885427.TI": "电子", "885537.TI": "计算机",
        "885546.TI": "通信", "885439.TI": "半导体", "885529.TI": "人工智能",
        "885528.TI": "食品饮料", "885430.TI": "医药生物", "885414.TI": "环保",
        "885473.TI": "银行", "885479.TI": "券商", "885452.TI": "房地产",
        "885424.TI": "交通运输", "885673.TI": "物流", "885416.TI": "钢铁",
        "885423.TI": "化工", "885550.TI": "有色金属", "885425.TI": "建材",
        "885699.TI": "水利",
    }

    sectors = []
    for code, name in CODES.items():
        try:
            data = THS_RQ(code, "latest;changeRatio", "")
            if data and data.errorcode == 0:
                df = data.data
                row = df.iloc[0]
                latest = float(row["latest"]) if "latest" in df.columns else 0
                chg = round(float(row["changeRatio"]), 2) if "changeRatio" in df.columns else 0
                sectors.append({"code": code, "name": name, "change_pct": chg, "index_value": latest})
        except Exception:
            pass

    try:
        THS_iFinDLogout()
    except Exception:
        pass

    if not sectors:
        return _empty(now)

    sorted_asc = sorted(sectors, key=lambda x: x["change_pct"])
    top_gainers = [s for s in sorted_asc if s["change_pct"] > 0][-10:]
    top_gainers.reverse()
    top_losers = [s for s in sorted_asc if s["change_pct"] < 0][:10]

    parties = [e for e in enterprises if e.get("role") == "甲方"]
    risks = []
    for p in parties:
        name = p.get("name", "")
        industry = p.get("industry", "")
        for s in top_losers:
            if _fuzzy_match(name, industry, s["name"]):
                chg = s["change_pct"]
                risks.append({
                    "enterprise": name, "sector": s["name"],
                    "sector_code": s["code"], "change_pct": chg,
                    "lead_stock": "",
                    "level": "red" if chg <= -5 else ("orange" if chg <= -2 else "yellow"),
                })

    return {
        "top_gainers": top_gainers, "top_losers": top_losers,
        "matched_risks": risks, "matched_opportunities": [],
        "missed_opportunities": [], "updated_at": now.isoformat(),
    }


def _empty(now) -> dict[str, Any]:
    return {
        "top_gainers": [], "top_losers": [],
        "matched_risks": [], "matched_opportunities": [],
        "missed_opportunities": [], "updated_at": now.isoformat(),
    }
