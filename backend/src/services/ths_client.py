"""
同花顺 iFinD HTTP API 客户端

提供企业财务数据、股票行情、债券信用信息的查询能力。
用于贷后监管系统中的深度企业风险分析。

API 文档: asserts/iFinD HTTP API 用户手册.pdf
SDK 文档: asserts/同花顺数据接口用户手册-Windows-Python.pdf
环境设置: asserts/同花顺数据接口环境设置.pdf

认证方式:
  refresh_token (长期) → access_token (短期, 通过 HTTP API 获取)
  refresh_token 从桌面客户端"设置-refresh_token查询/更新"获取
"""

from __future__ import annotations

import os
import time
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional

import requests
from loguru import logger


# ── 常量 ──────────────────────────────────────────────

BASE_URL = "https://quantapi.51ifind.com/api/v1"
DEFAULT_TIMEOUT = 30  # seconds


# ── 错误码映射 ─────────────────────────────────────────

ERROR_CODES: Dict[int, str] = {
    0: "成功",
    -1: "参数错误",
    -2: "用户或密码错误",
    -3: "token 过期或无效",
    -4: "无权限访问该接口",
    -5: "请求频率超限",
    -201: "重复登录",
}


class THSError(Exception):
    """同花顺 API 错误。"""

    def __init__(self, code: int, message: str) -> None:
        self.code = code
        self.message = message
        super().__init__(f"THS error {code}: {message}")


class THSClient:
    """同花顺 iFinD HTTP API 客户端。

    使用方式:
        client = THSClient(refresh_token="eyJ...")
        data = client.basic_data("600004.SH", ["latest", "open", "high", "low"])
    """

    def __init__(self, refresh_token: str = "") -> None:
        self._refresh_token = refresh_token or os.getenv("THS_REFRESH_TOKEN", "")
        self._access_token: str = ""
        self._token_expires_at: float = 0.0

    # ── 认证 ────────────────────────────────────────────

    def _ensure_token(self) -> str:
        """确保 access_token 有效，必要时自动刷新。"""
        if self._access_token and time.time() < self._token_expires_at:
            return self._access_token

        if not self._refresh_token:
            raise THSError(-3, "未配置 THS_REFRESH_TOKEN，请在 .env 中设置或传入参数")

        url = f"{BASE_URL}/get_access_token"
        headers = {
            "Content-Type": "application/json",
            "refresh_token": self._refresh_token,
        }
        try:
            resp = requests.post(url, headers=headers, timeout=DEFAULT_TIMEOUT)
            resp.raise_for_status()
            data = resp.json()
        except requests.RequestException as e:
            raise THSError(-3, f"获取 access_token 网络错误: {e}") from e

        if data.get("errorcode", -1) != 0:
            raise THSError(
                data.get("errorcode", -1),
                data.get("errmsg", "获取 access_token 失败"),
            )

        token_data = data.get("data", {})
        self._access_token = token_data.get("access_token", "")
        if not self._access_token:
            raise THSError(-3, "access_token 为空")

        # token 有效期通常为生成后数小时，保守设为 30 分钟
        self._token_expires_at = time.time() + 1800
        logger.debug("THS access_token 已获取，有效期至 {}", datetime.fromtimestamp(self._token_expires_at))
        return self._access_token

    def _auth_headers(self) -> Dict[str, str]:
        """获取带认证的请求头。"""
        return {
            "Content-Type": "application/json",
            "access_token": self._ensure_token(),
        }

    # ── 底层请求 ────────────────────────────────────────

    def _post(self, endpoint: str, json_data: Dict[str, Any]) -> Dict[str, Any]:
        """POST 请求封装。"""
        url = f"{BASE_URL}/{endpoint}"
        try:
            resp = requests.post(
                url,
                json=json_data,
                headers=self._auth_headers(),
                timeout=DEFAULT_TIMEOUT,
            )
            resp.raise_for_status()
            data = resp.json()
        except requests.RequestException as e:
            raise THSError(-1, f"API 请求失败 [{endpoint}]: {e}") from e

        errcode = data.get("errorcode", -1)
        if errcode != 0:
            errmsg = data.get("errmsg", ERROR_CODES.get(errcode, "未知错误"))
            raise THSError(errcode, errmsg)
        return data

    # ── 基本面数据 ──────────────────────────────────────

    def basic_data(
        self,
        codes: str,
        indicators: str,
        function_para: Optional[Dict[str, str]] = None,
    ) -> Dict[str, Any]:
        """获取基本面数据（财务报表、盈利预测、分红指标等）。

        Args:
            codes: 逗号分隔的同花顺代码，如 "600004.SH,300330.SZ"
            indicators: 分号分隔的指标名，如 "latest;open;high;low;amt"
            function_para: 可选函数参数，如 {"startdate": "2024-01-01"}

        Returns:
            {"tables": [...], "dataVol": N, ...}
        """
        payload: Dict[str, Any] = {
            "codes": codes,
            "indicators": indicators,
        }
        if function_para:
            payload["functionpara"] = function_para
        return self._post("basic_data_service", payload)

    def deep_basic_data(
        self,
        codes: str,
        indicators: str,
        function_para: Optional[Dict[str, str]] = None,
    ) -> Dict[str, Any]:
        """获取深度基本面数据（包含更多财务指标、自定义参数）。

        Args:
            codes: 逗号分隔的同花顺代码
            indicators: 分号分隔的指标名
            function_para: 函数参数，支持 report_date, data_type 等

        Returns:
            {"tables": [...], ...}
        """
        payload: Dict[str, Any] = {
            "codes": codes,
            "indicators": indicators,
        }
        if function_para:
            payload["functionpara"] = function_para
        return self._post("deep_basic_data_service", payload)

    # ── 行情数据 ────────────────────────────────────────

    def history_quotation(
        self,
        codes: str,
        indicators: str,
        start_date: str,
        end_date: str,
        function_para: Optional[Dict[str, str]] = None,
    ) -> Dict[str, Any]:
        """获取历史行情数据。

        Args:
            codes: 逗号分隔的同花顺代码
            indicators: 分号分隔的指标名 (open,high,low,close,amt,vol 等)
            start_date: 起始日期 "YYYY-MM-DD" / "YYYYMMDD"
            end_date: 结束日期
            function_para: 可选参数 (如复权类型)

        Returns:
            {"tables": [...], ...}
        """
        payload: Dict[str, Any] = {
            "codes": codes,
            "indicators": indicators,
            "startdate": start_date,
            "enddate": end_date,
        }
        if function_para:
            payload["functionpara"] = function_para
        return self._post("history_quotation", payload)

    def real_time_quotation(
        self, codes: str, indicators: str
    ) -> Dict[str, Any]:
        """获取实时行情数据。

        Args:
            codes: 逗号分隔的同花顺代码
            indicators: 分号分隔的指标名 (latest,open,high,low,amt,vol 等)

        Returns:
            {"tables": [...], ...}
        """
        return self._post(
            "real_time_quotation",
            {"codes": codes, "indicators": indicators},
        )

    def snap_shot(
        self,
        codes: str,
        indicators: str,
        start_time: Optional[str] = None,
        end_time: Optional[str] = None,
    ) -> Dict[str, Any]:
        """获取快照数据（分时级别行情）。

        Args:
            codes: 逗号分隔的同花顺代码
            indicators: 分号分隔的指标名
            start_time: 起始时间 "YYYY-MM-DD HH:mm:ss"
            end_time: 结束时间

        Returns:
            {"tables": [...], ...}
        """
        payload: Dict[str, Any] = {
            "codes": codes,
            "indicators": indicators,
        }
        if start_time:
            payload["starttime"] = start_time
        if end_time:
            payload["endtime"] = end_time
        return self._post("snap_shot", payload)

    # ── EDB 宏观经济数据 ────────────────────────────────

    def edb_query(
        self,
        indicators: str,
        function_para: Optional[Dict[str, str]] = None,
    ) -> Dict[str, Any]:
        """查询 EDB 宏观经济数据库。

        Args:
            indicators: 分号分隔的 EDB 指标代码，如 "M001620326;M002822183"
            function_para: 可选参数 {"startdate": "...", "enddate": "..."}

        Returns:
            {"tables": [...], ...}
        """
        payload: Dict[str, Any] = {"indicators": indicators}
        if function_para:
            payload["functionpara"] = function_para
        return self._post("edb_service", payload)

    # ── 债券 / 信用风险 ─────────────────────────────────

    def bond_data(
        self,
        codes: str,
        indicators: str,
        function_para: Optional[Dict[str, str]] = None,
    ) -> Dict[str, Any]:
        """获取债券相关数据。

        通过 basic_data_service 查询债券指标:
        - 债券评级 (bond_rating)
        - 票面利率 (coupon_rate)
        - 到期日 (maturity_date)
        - 违约状态 (default_status)

        Args:
            codes: 债券代码
            indicators: 债券相关指标
            function_para: 可选参数
        """
        return self.basic_data(codes, indicators, function_para)

    # ── 专题报告 ────────────────────────────────────────

    def thematic_report(
        self,
        report_type: str,
        function_para: Optional[Dict[str, str]] = None,
    ) -> Dict[str, Any]:
        """获取专题报告数据（行业分析、宏观研究等）。

        Args:
            report_type: 报告类型标识
            function_para: 可选参数
        """
        payload: Dict[str, Any] = {"report_type": report_type}
        if function_para:
            payload["functionpara"] = function_para
        return self._post("thematic_report_service", payload)

    # ── 贷后监管专用查询 ────────────────────────────────

    def get_company_financials(
        self,
        stock_code: str,
        report_type: str = "annual",
        years: int = 3,
    ) -> Dict[str, Any]:
        """获取企业核心财务指标（贷后监管专用）。

        查询: 营业收入、净利润、资产负债率、ROE、经营现金流、
              应收账款周转率、流动比率、利息保障倍数

        Args:
            stock_code: 股票代码，如 "600004.SH"
            report_type: 报告类型 annual/quarterly
            years: 查询年数

        Returns:
            结构化财务数据字典
        """
        indicators = (
            "latest;open;high;low;amt;vol;"                      # 行情
            "oper_rev;net_profit_is;debt_to_assets;"              # 营收/利润/负债率
            "roe;oper_cash_flow_ps;"                              # ROE/现金流
            "ar_turnover;current_ratio;icr"                       # 应收周转/流动比/利息保障
        )
        end_date = datetime.now().strftime("%Y-%m-%d")
        start_date = (datetime.now() - timedelta(days=years * 365)).strftime("%Y-%m-%d")

        try:
            # 深度基本面
            basic = self.deep_basic_data(
                codes=stock_code,
                indicators=indicators,
                function_para={
                    "startdate": start_date,
                    "enddate": end_date,
                    "data_type": report_type,
                },
            )
            # 历史行情（检测连续跌停等异常）
            hist = self.history_quotation(
                codes=stock_code,
                indicators="open;high;low;close;amt;vol;pre_close;change_ratio",
                start_date=(datetime.now() - timedelta(days=60)).strftime("%Y-%m-%d"),
                end_date=end_date,
            )
            return {
                "financials": basic,
                "recent_quotes": hist,
                "stock_code": stock_code,
                "query_time": datetime.now().isoformat(),
            }
        except THSError as e:
            logger.warning(f"同花顺查询 {stock_code} 失败: {e}")
            return {
                "financials": {},
                "recent_quotes": {},
                "stock_code": stock_code,
                "error": str(e),
                "query_time": datetime.now().isoformat(),
            }

    def get_credit_risk(
        self, stock_code: str
    ) -> Dict[str, Any]:
        """获取企业信用风险指标。

        查询: 债券评级、违约记录、股权质押、诉讼公告

        Args:
            stock_code: 股票代码

        Returns:
            信用风险数据字典
        """
        indicators = (
            "bond_rating;default_status;pledge_ratio;"            # 债券/质押
            "lawsuit_count;credit_rating;rating_outlook;"          # 诉讼/评级
            "z_score;altman_z"                                     # 风险模型
        )
        try:
            data = self.deep_basic_data(
                codes=stock_code,
                indicators=indicators,
                function_para={
                    "data_type": "latest",
                },
            )
            # 提取信用评级和预警信号
            tables = data.get("tables", [])
            signals = self._parse_credit_signals(tables)
            return {
                "raw_data": data,
                "signals": signals,
                "stock_code": stock_code,
                "query_time": datetime.now().isoformat(),
            }
        except THSError as e:
            logger.warning(f"同花顺信用风险查询 {stock_code} 失败: {e}")
            return {
                "raw_data": {},
                "signals": [],
                "stock_code": stock_code,
                "error": str(e),
                "query_time": datetime.now().isoformat(),
            }

    @staticmethod
    def _parse_credit_signals(tables: List[Dict]) -> List[Dict[str, str]]:
        """从 API 返回数据中提取信用预警信号。"""
        signals: List[Dict[str, str]] = []
        for table in tables:
            rows = table.get("table", [])
            for row in rows:
                # 解析评级相关字段
                if "bond_rating" in row and row["bond_rating"]:
                    rating = str(row["bond_rating"])
                    if any(kw in rating for kw in ["C", "D", "CC", "CCC"]):
                        signals.append({
                            "type": "bond_rating_downgrade",
                            "severity": "red",
                            "detail": f"债券评级: {rating}",
                        })
                if "rating_outlook" in row and "负面" in str(row.get("rating_outlook", "")):
                    signals.append({
                        "type": "rating_outlook_negative",
                        "severity": "orange",
                        "detail": "评级展望为负面",
                    })
        return signals

    def get_stock_anomalies(
        self, stock_code: str, lookback_days: int = 60
    ) -> Dict[str, Any]:
        """检测股票异常波动（连续跌停、放量下跌等）。

        用于贷后监管中识别企业股价异常 → 经营风险信号。

        Args:
            stock_code: 股票代码
            lookback_days: 回溯天数

        Returns:
            异常检测结果
        """
        end_date = datetime.now().strftime("%Y-%m-%d")
        start_date = (datetime.now() - timedelta(days=lookback_days)).strftime("%Y-%m-%d")

        try:
            data = self.history_quotation(
                codes=stock_code,
                indicators=(
                    "open;high;low;close;amt;vol;"
                    "pre_close;change_ratio;turnover_rate;"
                    "limit_down;limit_up"
                ),
                start_date=start_date,
                end_date=end_date,
            )

            tables = data.get("tables", [])
            anomalies = self._detect_anomalies(tables)
            return {
                "raw_data": data,
                "anomalies": anomalies,
                "stock_code": stock_code,
                "lookback_days": lookback_days,
                "query_time": datetime.now().isoformat(),
            }
        except THSError as e:
            logger.warning(f"同花顺异常检测 {stock_code} 失败: {e}")
            return {
                "raw_data": {},
                "anomalies": [],
                "stock_code": stock_code,
                "error": str(e),
                "query_time": datetime.now().isoformat(),
            }

    @staticmethod
    def _detect_anomalies(tables: List[Dict]) -> List[Dict[str, Any]]:
        """从历史行情中检测异常模式。

        检测项:
        - 连续跌停 (收盘价连续 N 日达到跌停价)
        - 放量下跌 (跌幅 > 5% 且成交量 > 20日均量 2 倍)
        - 持续下跌 (连续 5 日以上收盘价下降)
        - 跳空低开 (开盘价 < 前日收盘价 * 0.95)
        """
        anomalies: List[Dict[str, Any]] = []
        for table in tables:
            rows = table.get("table", [])
            if len(rows) < 3:
                continue

            # 连续跌停检测
            consecutive_limit_down = 0
            for row in rows:
                close = float(row.get("close", 0))
                pre_close = float(row.get("pre_close", 0))
                if pre_close > 0 and close > 0:
                    change_pct = (close - pre_close) / pre_close
                    if change_pct <= -0.098:  # ~跌停 (-10%)
                        consecutive_limit_down += 1
                    else:
                        if consecutive_limit_down >= 3:
                            anomalies.append({
                                "type": "consecutive_limit_down",
                                "severity": "red",
                                "detail": f"连续 {consecutive_limit_down} 个交易日跌停",
                            })
                        consecutive_limit_down = 0

            # 持续下跌检测
            close_prices = [
                float(r.get("close", 0)) for r in rows if float(r.get("close", 0)) > 0
            ]
            if len(close_prices) >= 5:
                recent_5 = close_prices[-5:]
                if all(recent_5[i] < recent_5[i - 1] for i in range(1, len(recent_5))):
                    total_decline = (recent_5[-1] - recent_5[0]) / recent_5[0]
                    if total_decline <= -0.10:
                        anomalies.append({
                            "type": "sustained_decline",
                            "severity": "orange",
                            "detail": f"连续 5 日下跌，累计跌幅 {abs(total_decline) * 100:.1f}%",
                        })

        return anomalies


# ── 便捷工厂函数 ──────────────────────────────────────


def create_client(refresh_token: str = "") -> THSClient:
    """创建同花顺客户端实例。

    Args:
        refresh_token: 同花顺 refresh_token，为空则从环境变量 THS_REFRESH_TOKEN 读取
    """
    return THSClient(refresh_token=refresh_token)
