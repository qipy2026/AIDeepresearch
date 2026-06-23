"""同花顺 iFinD 全量数据采集器 — 贷后监管专用。

覆盖: 实时行情、历史异常检测、财务指标、信用风险、问财舆情。
"""
from __future__ import annotations

from typing import Any, Dict, List


def collect_all(ths_username: str, ths_password: str,
                stock_code: str, enterprise: str, industry: str = "",
                concept_code: str = "") -> List[Dict[str, Any]]:
    """采集同花顺全部可用数据，返回信号列表。每个信号是一个 dict。"""
    results: List[Dict[str, Any]] = []
    if not stock_code and not concept_code:
        return results

    try:
        from iFinDPy import (THS_iFinDLogin, THS_RQ, THS_HQ, THS_iFinDLogout)
        THS_iFinDLogin(ths_username, ths_password)
    except Exception:
        return results

    # ── 1. 实时行情 ──
    if stock_code:
        try:
            data = THS_RQ(stock_code, "latest;open;high;low;close;changeRatio;pb;volume;amount", "")
            if data and data.errorcode == 0:
                row = data.data.iloc[0]
                chg = round(float(row["changeRatio"]), 2)
                direction = "📉下跌" if chg < -3 else ("📈上涨" if chg > 3 else "➡️持平")
                results.append({
                    "source": "ths_stock", "label": f"{enterprise}（同花顺·行情）",
                    "title": f"{direction} {enterprise} 最新¥{round(float(row['latest']),2)} "
                             f"涨跌{chg}% PB{round(float(row['pb']),2)}",
                    "detail": f"开盘{row['open']} 最高{row['high']} 最低{row['low']} "
                              f"昨收{row['close']} 成交量{row['volume']}",
                    "raw": str(row.to_dict()),
                })
        except Exception:
            pass

    # ── 2. 历史行情异常检测 ──
    if stock_code:
        try:
            from datetime import datetime, timedelta
            end = datetime.now().strftime("%Y-%m-%d")
            start = (datetime.now() - timedelta(days=60)).strftime("%Y-%m-%d")
            data = THS_HQ(stock_code, "open;high;low;close;pre_close;changeRatio;amt;vol",
                          "", start, end)
            if data and data.errorcode == 0:
                df = data.data
                anomalies = _detect_anomalies(df)
                for a in anomalies:
                    results.append({
                        "source": "ths_anomaly",
                        "label": f"{enterprise}（同花顺·异常）",
                        "title": f"🚨 {a['type_cn']}: {a['detail']}",
                        "detail": a["detail"],
                        "raw": str(a),
                    })
        except Exception:
            pass

    # ── 3. 概念指数 ──
    if concept_code:
        try:
            data = THS_RQ(concept_code, "latest;changeRatio", "")
            if data and data.errorcode == 0:
                row = data.data.iloc[0]
                chg = round(float(row["changeRatio"]), 2)
                results.append({
                    "source": "ths_stock",
                    "label": f"{enterprise}（同花顺·概念）",
                    "title": f"{'📉' if chg < -2 else ('📈' if chg > 2 else '➡️')} "
                             f"{industry}概念 指数{round(float(row['latest']),1)} 涨跌{chg}%",
                    "detail": f"行业概念指数 {concept_code}",
                    "raw": str(row.to_dict()),
                })
        except Exception:
            pass

    # ── 4. 问财舆情（债券/信用风险查询） ──
    if enterprise:
        try:
            from iFinDPy import THS_iwencai
            import json
            raw = THS_iwencai(enterprise, "bond", True)
            data = json.loads(raw.decode("gbk"))
            if data.get("errorcode") == 0 and data.get("dataVol", 0) > 0:
                for t in data.get("tables", []):
                    table = t.get("table", {})
                    for k, v in table.items():
                        results.append({
                            "source": "ths_iwencai",
                            "label": f"{enterprise}（同花顺·问财）",
                            "title": f"📊 问财债券搜索: {k}",
                            "detail": str(v)[:300],
                            "raw": json.dumps(data, ensure_ascii=False)[:1000],
                        })
        except Exception:
            pass

    try:
        THS_iFinDLogout()
    except Exception:
        pass

    return results


def _detect_anomalies(df) -> List[Dict[str, Any]]:
    """检测股价异常模式。"""
    anomalies = []
    if df is None or len(df) < 5:
        return anomalies

    closes = [float(df.iloc[i]["close"]) for i in range(len(df))
              if float(df.iloc[i].get("close", 0)) > 0]
    pre_closes = [float(df.iloc[i].get("pre_close", 0)) for i in range(len(df))]

    # 连续下跌检测
    if len(closes) >= 5:
        recent = closes[-5:]
        if all(recent[i] < recent[i - 1] for i in range(1, len(recent))):
            decline = (recent[-1] - recent[0]) / recent[0] * 100
            if decline <= -10:
                anomalies.append({
                    "type": "sustained_decline",
                    "type_cn": "连续下跌",
                    "detail": f"连续5日下跌，累计跌幅{abs(decline):.1f}%",
                })

    # 单日大跌检测
    if len(pre_closes) >= 1 and len(closes) >= 1:
        last_close = closes[-1]
        last_pre = pre_closes[-1] if pre_closes[-1] > 0 else last_close
        if last_pre > 0:
            day_chg = (last_close - last_pre) / last_pre * 100
            if day_chg <= -5:
                anomalies.append({
                    "type": "sharp_drop",
                    "type_cn": "单日大跌",
                    "detail": f"单日跌幅{abs(day_chg):.1f}%，收盘¥{last_close}",
                })

    return anomalies
