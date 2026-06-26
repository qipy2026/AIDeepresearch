"""最终报告（LangChain LLM），支持标准报告和贷后周报两种模式。"""

from __future__ import annotations

import os
import re
from datetime import date, datetime
from pathlib import Path
from typing import Any, Dict, List, Optional, TypedDict

from config import Configuration
from core.llm import invoke_llm
from models import SummaryState
from prompts import report_writer_instructions, weekly_report_writer_instructions
from services.notes_store import NotesStore
from loguru import logger
from services.text_processing import strip_tool_calls
from utils import strip_thinking_tokens


REFS_DIR = Path(__file__).resolve().parent.parent.parent / "references"

# ── 可调优常量 ──────────────────────────────────────────


def _load_keywords() -> List[str]:
    """从 keywords.yaml 加载负面风险关键词（三组词组合并）。"""
    import yaml

    _p = Path(__file__).resolve().parent.parent.parent / "config" / "keywords.yaml"
    if _p.exists():
        with open(_p, "r", encoding="utf-8") as f:
            data = yaml.safe_load(f) or {}
        return data.get("fatal", []) + data.get("severe", []) + data.get("watch", [])
    return ["风险", "下降", "萎缩", "违约", "处罚", "下滑", "亏损"]


# 负面风险关键词，用于文本扫描计数
NEGATIVE_RISK_KEYWORDS: List[str] = _load_keywords()
# 视频巡检人数下降阈值（初始 20%，基于 3 倍标准差统计控制，后续根据历史误报率调优）
HEADCOUNT_TREND_THRESHOLD: float = 0.20
# 趋势计算所需最少有效数据周数
MIN_TREND_WEEKS: int = 3
# 字段默认值（缺失时优雅降级）
FIELD_DEFAULTS: dict[str, str] = {
    "loan_amount": "未披露",
    "industry": "未分类",
    "enterprise": "未知企业",
}


# ── 结构化数据模型 ──────────────────────────────────────


class WeeklyData(TypedDict, total=False):
    """贷后周报结构化上下文数据结构。字段缺失时格式化器使用优雅降级。"""

    enterprise: str
    industry: str
    loan_amount: str
    report_date: str
    report_period_start: str
    report_period_end: str
    ref_text: str
    risk: Dict[str, int]
    warnings_signals: Optional[List[Dict[str, Any]]]
    warnings_summary: Optional[Dict[str, Any]]
    headcount_trend: Optional[Dict[str, Any]]
    key_snapshots: Optional[List[Dict[str, Any]]]
    camera_aggregated: Optional[List[Dict[str, Any]]]  # 完整小时级聚合快照数据
    party_a_signals: Optional[List[Dict[str, Any]]]
    industry_data: Optional[Dict[str, Any]]



# ── ReportingService ────────────────────────────────────


class ReportingService:
    def __init__(
        self,
        config: Configuration,
        notes: NotesStore | None = None,
        report_style: str = "standard",
    ) -> None:
        self._config = config
        self._notes = notes
        self._style = report_style

    # ── 视频巡检趋势 ───────────────────────────────────────

    @staticmethod
    def _attach_key_snapshots(
        aggregated: List[Dict[str, Any]],
        raw_snapshots: List[Dict[str, Any]],
    ) -> None:
        """从原始快照记录中找到关键时刻并回填 snapshot_path 到聚合结果。

        关键时刻: 人数峰值、人数谷值(>0)、最接近9:00、最接近14:00。
        """
        if not raw_snapshots:
            return

        # 按 person_count 排序找峰值和谷值
        by_count = sorted(raw_snapshots,
                          key=lambda r: r.get("person_count", 0))
        valley = by_count[0]  # 最小值
        peak = by_count[-1]   # 最大值

        # 按时间接近 9:00 和 14:00 找最近记录
        def _minutes_from_target(rec: dict, target_hour: int) -> float:
            ts = rec.get("timestamp", "")
            try:
                from datetime import datetime as _dt
                t = _dt.fromisoformat(ts.replace("Z", "+00:00"))
                return abs((t.hour + t.minute / 60) - target_hour)
            except (ValueError, TypeError):
                return float("inf")

        near_9am = min(raw_snapshots,
                       key=lambda r: _minutes_from_target(r, 9), default=None)
        near_2pm = min(raw_snapshots,
                       key=lambda r: _minutes_from_target(r, 14), default=None)

        # 构建关键时刻 snapshot_path 集合 (去重)
        key_paths = {}
        for label, snap in [("peak", peak), ("valley", valley),
                            ("9am", near_9am), ("2pm", near_2pm)]:
            if snap and snap.get("snapshot_path"):
                key_paths[snap["snapshot_path"]] = label

        # 匹配聚合桶: 原始记录的 timestamp 前缀匹配聚合桶的 snapshot_date
        for row in aggregated:
            bucket = row.get("snapshot_date", "")
            for snap_path, label in key_paths.items():
                # 找到这个 snapshot_path 对应的原始记录 timestamp
                snap_ts = next(
                    (r["timestamp"] for r in [peak, valley, near_9am, near_2pm]
                     if r and r.get("snapshot_path") == snap_path),
                    "",
                )
                # timestamp 格式 "2026-06-24T14:00:00+00:00"
                # bucket 格式 "2026-06-24T14"
                if snap_ts and snap_ts.startswith(bucket):
                    row["snapshot_path"] = snap_path
                    break  # 一个桶只匹配一张截图

    @staticmethod
    def _sync_snapshot_images(snapshots: List[Dict[str, Any]]) -> None:
        """将快照图片从 search 项目目录按需复制到本项目本地目录。

        仅复制尚不存在的文件；源不可达或复制失败时清空该记录的 snapshot_path，
        不阻塞报告生成。
        """
        import shutil

        src_dir = os.getenv("CAMERA_SNAPSHOT_SRC", "")
        local_dir = os.getenv("CAMERA_SNAPSHOT_LOCAL", "./snapshot_data")

        if not src_dir:
            logger.warning("CAMERA_SNAPSHOT_SRC 未配置，跳过图片同步")
            for s in snapshots:
                s["snapshot_path"] = ""
            return

        # 确保本地目录存在
        Path(local_dir).mkdir(parents=True, exist_ok=True)

        for s in snapshots:
            sp = s.get("snapshot_path", "")
            if not sp:
                continue

            # 提取文件名（兼容 Windows \ 和 POSIX /）
            fname = sp.replace("\\", "/").split("/")[-1]
            src_path = Path(src_dir) / fname

            if not src_path.exists():
                logger.warning("快照图片源文件不存在: {}，跳过", src_path)
                s["snapshot_path"] = ""
                continue

            dst_path = Path(local_dir) / fname
            if not dst_path.exists():
                try:
                    shutil.copy2(str(src_path), str(dst_path))
                    logger.debug("快照图片已复制: {} -> {}", src_path, dst_path)
                except (OSError, shutil.Error) as _e:
                    logger.warning("快照图片复制失败: {} -> {}, 错误={}", src_path, dst_path, _e)
                    s["snapshot_path"] = ""
                    continue

            # 更新为可 serve 的路径（只要文件名，路由会拼接本地目录）
            s["snapshot_path"] = fname

    @staticmethod
    def _build_video_inspection_section(
        aggregated: List[Dict[str, Any]],
        key_snapshots: List[Dict[str, Any]],
        headcount_trend: Optional[Dict[str, Any]],
    ) -> str:
        """纯代码生成"四、现场视频巡检"章节的 Markdown。

        不依赖 LLM——所有数据直接从已读取的摄像头数据库拼装。
        图片复制已在 _sync_snapshot_images 中完成，snapshot_path 此时为纯文件名。
        """
        lines = ["## 四、现场视频巡检", ""]
        lines.append("（注：一个企业通常配置4-6个摄像头点位，以下为巡检数据）")
        lines.append("")

        # ── 子节 1：重点时段统计 ──
        lines.append("### 重点时段统计")
        lines.append("")
        if not aggregated:
            lines.append("| 时段 | 时间戳 | 人数 | 场景 | 备注情况 |")
            lines.append("|------|--------|------|------|---------|")
            lines.append("| [暂无巡检数据] | | | | |")
            lines.append("")
        else:
            # 按日期分组，提取 09:00 和 14:00 人数
            from collections import defaultdict
            daily: Dict[str, Dict[int, int]] = defaultdict(dict)
            for s in aggregated:
                bucket = s.get("snapshot_date", "")  # "YYYY-MM-DDTHH"
                if "T" not in bucket:
                    continue
                date_str, hour_str = bucket.split("T", 1)
                hour = int(hour_str) if hour_str.isdigit() else None
                hc = s.get("headcount", 0)
                if hour is not None:
                    daily[date_str][hour] = hc

            lines.append("| 日期 | 09:00 人数 | 14:00 人数 | 日均人数 |")
            lines.append("|------|-----------|-----------|---------|")
            for day in sorted(daily.keys()):
                h9 = daily[day].get(9)
                h14 = daily[day].get(14)
                all_vals = list(daily[day].values())
                avg = round(sum(all_vals) / len(all_vals)) if all_vals else 0
                s9 = str(h9) if h9 is not None else "—"
                s14 = str(h14) if h14 is not None else "—"
                lines.append(f"| {day} | {s9} | {s14} | {avg} |")
            lines.append("")

        # ── 子节 2：历史对比 ──
        lines.append("### 历史对比")
        lines.append("")
        if headcount_trend and headcount_trend.get("status") not in ("insufficient", None):
            current_avg = headcount_trend.get("current_avg")
            prior_avg = headcount_trend.get("prior_avg")
            delta_pct = headcount_trend.get("delta_pct")
            message = headcount_trend.get("message", "")

            from datetime import date, timedelta
            today = date.today()
            # 本周范围
            week_start = today - timedelta(days=today.weekday())
            week_end = week_start + timedelta(days=6)

            lines.append("| 周次 | 日期范围 | 日均人数 | 变化 |")
            lines.append("|------|---------|---------|------|")
            cur_str = f"{current_avg:.1f}" if current_avg is not None else "N/A"
            lines.append(
                f"| 本周 | {week_start.strftime('%m-%d')} ~ {week_end.strftime('%m-%d')} "
                f"| {cur_str} | — |"
            )
            if prior_avg is not None and delta_pct is not None:
                prior_start = week_start - timedelta(days=7)
                prior_end = week_start - timedelta(days=1)
                prior_str = f"{prior_avg:.1f}"
                direction = "+" if delta_pct > 0 else ""
                pct_str = f"{direction}{delta_pct * 100:.1f}%"
                lines.append(
                    f"| 前3周 | {prior_start.strftime('%m-%d')} ~ {prior_end.strftime('%m-%d')} "
                    f"| {prior_str} | {pct_str} |"
                )
            lines.append("")
            lines.append(f"趋势说明：{message}")
            lines.append("")
        else:
            lines.append("暂无历史对比数据")
            lines.append("")

        # ── 子节 3：重点时段照片记录 ──
        lines.append("### 重点时段照片记录")
        lines.append("")
        if key_snapshots:
            for s in key_snapshots:
                fname = s.get("snapshot_path", "").replace("\\", "/").split("/")[-1]
                if not fname:
                    continue
                lines.append(
                    f"![{s.get('snapshot_date', '')} {s.get('headcount', '?')}人]"
                    f"(/snapshots/{fname})"
                )
            lines.append("")
        else:
            lines.append("暂无快照数据")
            lines.append("")

        return "\n".join(lines) + "\n"

    @staticmethod
    def _read_camera_snapshots(enterprise: str, weeks: int = 4) -> List[Dict[str, Any]]:
        """读取企业指定周数内的摄像头快照人数数据。

        从 search 项目的 SQLite 数据库（counts.db）直接读取，
        不再依赖 search 项目 HTTP API。DB 不可用或配置缺失时优雅降级，返回空列表。

        enterprise 参数当前未使用——单摄场景下所有企业共享同一摄像头数据。
        保留此参数以便后续多摄像头对应多企业时按 enterprise 筛选 camera_id。
        """
        import sqlite3
        from contextlib import closing

        db_path = os.getenv("CAMERA_DB_PATH", "")
        if not db_path:
            logger.warning("CAMERA_DB_PATH 未配置，摄像头数据不可用")
            return []

        try:
            with closing(sqlite3.connect(db_path)) as conn:
                conn.row_factory = sqlite3.Row

                # 1. 聚合时序数据（替代 /api/counts/timeseries?camera_id=1&days=N）
                rows = conn.execute(
                    """SELECT
                         strftime('%Y-%m-%dT%H', recorded_at) AS bucket,
                         AVG(person_count) AS avg_count
                       FROM counts
                       WHERE camera_id = 1
                         AND recorded_at >= datetime('now', '-' || ? || ' days')
                         AND person_count IS NOT NULL
                       GROUP BY bucket
                       ORDER BY bucket""",
                    (weeks * 7,),
                ).fetchall()

                result = [
                    {
                        "snapshot_date": row["bucket"],
                        "headcount": round(row["avg_count"]),
                        "snapshot_path": "",
                    }
                    for row in rows
                ]

                # 2. 原始快照记录（替代 /api/counts/timeseries?bucket=raw&from=...）
                from datetime import datetime as _dt, timedelta as _td, timezone as _tz
                from_ts = (_dt.now(_tz.utc) - _td(days=weeks * 7)).strftime("%Y-%m-%d")
                raw_rows = conn.execute(
                    """SELECT recorded_at AS timestamp, person_count, snapshot_path
                       FROM counts
                       WHERE camera_id = 1
                         AND recorded_at >= ?
                         AND snapshot_path != ''
                         AND person_count IS NOT NULL
                       ORDER BY recorded_at DESC""",
                    (from_ts,),
                ).fetchall()

                if raw_rows:
                    snapshots = [dict(r) for r in raw_rows]
                    ReportingService._attach_key_snapshots(result, snapshots)

                    # 3. 图片按需同步
                    ReportingService._sync_snapshot_images(result)

                return result
        except (sqlite3.Error, sqlite3.DatabaseError) as _e:
            logger.warning(
                "摄像头 SQLite 数据库读取失败，企业={}，DB={}，错误={}，降级为空数据",
                enterprise, db_path, _e,
            )
            return []

    @staticmethod
    def _compute_headcount_trend(
        enterprise: str, weeks: int = 4
    ) -> Dict[str, Any]:
        """计算企业视频巡检人数趋势。

        从 CameraSnapshot 读取最近指定周数的人数数据，
        对比本周均值与前 3 周均值的百分比变化。

        Returns:
            {
                "status": "insufficient" | "anomaly" | "stable" | "decline" | "growth",
                "weeks_data": [...],
                "current_avg": float | None,
                "prior_avg": float | None,
                "delta_pct": float | None,
                "message": str,
            }
        """
        snapshots = ReportingService._read_camera_snapshots(enterprise, weeks)

        # 数据不足
        if len(snapshots) < MIN_TREND_WEEKS:
            return {
                "status": "insufficient",
                "weeks_data": snapshots,
                "current_avg": None,
                "prior_avg": None,
                "delta_pct": None,
                "message": "数据不足，暂无法生成趋势",
            }

        # 按天聚合人数（去重同日多条快照取均值）
        daily_counts: Dict[str, List[int]] = {}
        for s in snapshots:
            day = s.get("snapshot_date", "")
            count = s.get("headcount", 0)
            if day:
                daily_counts.setdefault(day, []).append(count)

        daily_avgs = sorted(
            [(d, sum(c) / len(c)) for d, c in daily_counts.items()],
            key=lambda x: x[0],
            reverse=True,
        )

        # 不足最小周数（按天去重后）
        if len(daily_avgs) < MIN_TREND_WEEKS:
            return {
                "status": "insufficient",
                "weeks_data": daily_avgs,
                "current_avg": None,
                "prior_avg": None,
                "delta_pct": None,
                "message": "数据不足，暂无法生成趋势",
            }

        # 本周 = 最近 7 天, 前 3 周 = 第 8-28 天
        current_week = [c for d, c in daily_avgs[:7]]
        prior_weeks = [c for d, c in daily_avgs[7:28]]

        current_avg = sum(current_week) / len(current_week) if current_week else 0.0
        prior_avg = sum(prior_weeks) / len(prior_weeks) if prior_weeks else 0.0

        # 全零数据检测（T8）—— 摄像头可能未配置或故障
        if current_avg == 0.0 and prior_avg == 0.0:
            return {
                "status": "anomaly",
                "weeks_data": daily_avgs,
                "current_avg": 0.0,
                "prior_avg": 0.0,
                "delta_pct": 0.0,
                "message": "数据异常：连续 4 周人数为 0，请检查摄像头配置",
            }

        if prior_avg == 0.0:
            delta_pct = 0.0
        else:
            delta_pct = (current_avg - prior_avg) / prior_avg

        if delta_pct <= -HEADCOUNT_TREND_THRESHOLD:
            status = "decline"
            direction = "↓"
        elif delta_pct >= HEADCOUNT_TREND_THRESHOLD:
            status = "growth"
            direction = "↑"
        else:
            status = "stable"
            direction = "→"

        pct_str = f"{abs(delta_pct) * 100:.1f}%"
        if status == "decline":
            message = f"{direction} 下降 {pct_str}，触发关注阈值"
        elif status == "growth":
            message = f"{direction} 增长 {pct_str}"
        else:
            message = f"{direction} 稳定，变化 {pct_str}"

        return {
            "status": status,
            "weeks_data": daily_avgs,
            "current_avg": round(current_avg, 1),
            "prior_avg": round(prior_avg, 1),
            "delta_pct": round(delta_pct, 4),
            "message": message,
        }

    # ── 周报辅助方法 ──────────────────────────────────────────

    @staticmethod
    def _extract_enterprise_from_topic(topic: str) -> str:
        """从调查主题中提取企业名。先匹配含公司后缀的，再回退到 enterprises.yaml 已知企业名。"""
        m = re.search(r"([一-鿿]{2,20}(?:有限公司|有限责任公司|分公司))", topic)
        if m:
            return m.group(1)
        # Fallback: match against known enterprise names from YAML (covers names
        # without standard company suffixes like 新街里南城都汇, 四川能投润嘉)
        ents = ReportingService._load_enterprises_yaml()
        for ent in ents:
            name = ent.get("name", "")
            if name and len(name) >= 3 and name in topic:
                return name
        return topic.strip()

    @staticmethod
    def _calc_risk_counts_from_tasks(tasks: list) -> dict:
        """遍历所有任务搜索结果，统计负面关键词命中数生成风险计数。"""
        total_hits = 0
        for t in tasks:
            text = f"{t.summary or ''} {t.sources_summary or ''}"
            total_hits += sum(1 for kw in NEGATIVE_RISK_KEYWORDS if kw in text)
        if total_hits >= 3:
            return {"red": 1, "orange": 0, "yellow": total_hits, "total": total_hits + 1}
        elif total_hits >= 1:
            return {"red": 0, "orange": 0, "yellow": total_hits, "total": total_hits}
        return {"red": 0, "orange": 0, "yellow": 0, "total": 0}

    @staticmethod
    def _read_reference_doc(enterprise_name: str) -> str:
        """读取参考文档（人工维护的企业结构化数据）。"""
        ref_path = REFS_DIR / f"{enterprise_name}.md"
        if ref_path.exists():
            return ref_path.read_text(encoding="utf-8")
        return ""

    # ── 微服务模式：搜索 → RAG → 无相关内容 ──────────────────

    def _get_field_value(
        self, field_key: str, search_result: str | None, enterprise: str
    ) -> str:
        """微服务模式：先用搜索结果，失败走 RAG，再失败返回无相关内容。"""
        if search_result and search_result.strip() not in ("", "暂无可用信息"):
            return search_result.strip()
        ref_text = self._read_reference_doc(enterprise)
        if ref_text:
            rag_result = self._rag_match(field_key, ref_text)
            if rag_result:
                return rag_result
        return "无相关内容"

    @staticmethod
    def _rag_match(field_key: str, ref_text: str, enterprise: str = "") -> str | None:
        """查询 ChromaDB 向量库。不再使用关键词匹配文本文件。"""
        from services.rag_service import query as rag_query

        result = rag_query(field_key, enterprise, n_results=1)
        return result if result else None

    @staticmethod
    def _load_enterprises_yaml() -> list[dict]:
        """加载 enterprises.yaml 企业列表。"""
        import yaml
        from pathlib import Path as _Path

        _p = _Path(__file__).resolve().parent.parent.parent / "config" / "enterprises.yaml"
        if not _p.exists():
            return []
        with open(_p, "r", encoding="utf-8") as f:
            data = yaml.safe_load(f) or {}
        return data.get("enterprises", [])

    @classmethod
    def _get_enterprise_field(cls, enterprise_name: str, field: str) -> str:
        """从 enterprises.yaml 按企业名查询字段值。无匹配返回空字符串。"""
        ents = cls._load_enterprises_yaml()
        for ent in ents:
            if ent.get("name") == enterprise_name:
                val = ent.get(field, "")
                return str(val) if val else ""
        return ""

    @staticmethod
    def _read_warnings_from_db(enterprise: str) -> dict:
        """从 SQLite warning_log 读取企业预警数据。

        Returns dict with:
          signals: 高危信号列表 (red/orange/yellow)
          counts: 按 severity 统计 {red:N, orange:N, yellow:N, normal:N}
          total: 预警总数
          latest_time: 最新预警时间
        """
        from warning_db import WarningDB
        db = WarningDB()
        signals = db.get_signals_summary(enterprise, limit=20)
        counts = db.get_warnings_grouped_by_severity(enterprise)
        total = sum(counts.values())
        latest = signals[0]["created_at"] if signals else ""
        return {
            "signals": signals,
            "counts": counts,
            "total": total,
            "latest_time": latest,
        }

    def _collect_sources(self, tasks: list) -> str:
        """从所有任务中收集来源链接。"""
        sources = []
        for t in tasks:
            if t.sources_summary:
                for line in t.sources_summary.split("\n"):
                    line = line.strip()
                    if line.startswith("*") and " : " in line:
                        sources.append(line.lstrip("* ").strip())
        return "\n".join(f"- {s}" for s in sources) if sources else "无相关内容"

    # ── 行业宏观数据采集 ──────────────────────────────────

    @staticmethod
    def _fetch_industry_data(
        debtor_industry: str = "",
        related_industries: list[str] | None = None,
    ) -> Dict[str, Any]:
        """三层百度实时搜索 + 行业板块扫描 → 真正全行业覆盖的宏观数据。

        层1: 宏观经济大盘（4 query，不限行业）
        层2: 主体行业聚焦（3 query，债务企业所在行业）
        层3: 供应链相关行业（每行业 2 query，甲方的行业）
        板块扫描: 东财80板块+THS27概念涨跌
        """

        def _safe_baidu_search(query: str, max_results: int = 5) -> list[str]:
            try:
                from services.web_search import _search_baidu
                results = _search_baidu(query, max_results=max_results)
                return [r.get("title", "") for r in results if r.get("title")]
            except Exception:
                return []

        try:
            all_titles: list[str] = []
            policy_titles: list[str] = []
            risk_titles: list[str] = []

            # ═══ 层1: 宏观经济大盘（不限行业） ═══
            macro_queries = [
                "2026 中国经济 宏观 政策 趋势",
                "2026 重点行业 监管 政策 新规",
                "2026 行业 发展 风险 机遇 热点",
                "2026 消费 地产 制造 科技 经济 趋势",
            ]
            for q in macro_queries:
                titles = _safe_baidu_search(q, max_results=5)
                all_titles.extend(titles[:3])
                policy_titles.extend(titles[:2])

            # ═══ 层2: 主体行业聚焦（债务企业所在行业） ═══
            if debtor_industry:
                debtor_queries = [
                    f"{debtor_industry} 行业 政策 监管 2026",
                    f"{debtor_industry} 行业 风险 趋势 2026",
                    f"{debtor_industry} 市场 规模 分析 2026",
                ]
                for q in debtor_queries:
                    titles = _safe_baidu_search(q, max_results=5)
                    all_titles.extend(titles[:3])
                    if "风险" in q:
                        risk_titles.extend(titles[:3])
                    if "政策" in q:
                        policy_titles.extend(titles[:2])

            # ═══ 层3: 供应链相关行业（甲方所在行业） ═══
            for rel_ind in (related_industries or []):
                if rel_ind == debtor_industry:
                    continue  # 去重：与主体行业相同则跳过
                rel_queries = [
                    f"{rel_ind} 行业 动态 风险 2026",
                    f"{rel_ind} 行业 政策 趋势 2026",
                ]
                for q in rel_queries:
                    titles = _safe_baidu_search(q, max_results=3)
                    all_titles.extend(titles[:2])
                    if "风险" in q:
                        risk_titles.extend(titles[:2])

            # ═══ 行业板块扫描（东财+THS 缓存） ═══
            sector_events: list[str] = []
            try:
                from services.industry_scanner import scan_and_match
                import yaml
                from pathlib import Path
                _ep = Path(__file__).resolve().parent.parent.parent / "config" / "enterprises.yaml"
                with open(_ep, "r", encoding="utf-8") as _f:
                    _ents = yaml.safe_load(_f).get("enterprises", [])
                scan = scan_and_match(_ents)
                for s in (scan.get("top_gainers") or [])[:5]:
                    sector_events.append(
                        f"📈 {s['name']} +{s['change_pct']}%")
                for s in (scan.get("top_losers") or [])[:5]:
                    sector_events.append(
                        f"📉 {s['name']} {s['change_pct']}%")
            except Exception:
                pass

            # 去重
            seen: set[str] = set()
            unique_titles: list[str] = []
            for t in all_titles:
                if t not in seen:
                    seen.add(t)
                    unique_titles.append(t)

            has_sector = bool(sector_events)
            has_baidu = bool(unique_titles)

            industry_label = debtor_industry or "全行业"
            return {
                "industry": industry_label,
                "industry_status": (
                    "全行业覆盖（宏观大盘+主体行业+供应链+板块扫描）"
                    if (has_sector or has_baidu)
                    else "暂无数据"
                ),
                "key_indicators": (
                    "; ".join(unique_titles[:10]) if unique_titles
                    else f"行业数据分析待获取（{industry_label}）"
                ),
                "major_events": sector_events + unique_titles[:12],
                "policy_direction": "中性",
                "policy_detail": (
                    "; ".join(policy_titles[:5]) if policy_titles
                    else "暂无最新政策信息"
                ),
                "risk_warning": (
                    "; ".join(risk_titles[:3]) if risk_titles
                    else ("行业板块存在下跌信号" if any(
                        "📉" in e for e in sector_events)
                    else "未发现明显行业风险")
                ),
                "signals": [],
                "source": "三层百度实时搜索（宏观+主体行业+供应链）+ 板块扫描",
                "macro_available": has_baidu,
                "industry_available": has_sector or has_baidu,
            }
        except Exception as e:
            logger.warning(f"行业数据提取失败: {e}")
            return {
                "industry": debtor_industry or "全行业",
                "industry_status": "暂无数据",
                "key_indicators": "行业数据分析待获取",
                "major_events": [],
                "policy_direction": "中性",
                "policy_detail": "暂无最新政策信息",
                "risk_warning": "未发现明显负面信号",
                "signals": [],
                "source": "百度实时搜索",
                "macro_available": False,
                "industry_available": False,
            }

    @staticmethod
    def _fetch_party_a_signals(enterprise: str) -> list:
        """从 enterprises.yaml + warning_db 获取甲方（核心企业）经营信号。

        Returns:
            [{name, industry, parent, signals, signal_count}, ...]
        """
        from warning_db import WarningDB

        # 1. 找出所有 debtor==enterprise 且 role=="甲方" 的企业
        ents = ReportingService._load_enterprises_yaml()
        parties = [
            e for e in ents
            if e.get("debtor") == enterprise and e.get("role") == "甲方"
        ]

        if not parties:
            return []

        # 2. 对每个甲方从 warning_db 拉取信号
        db = WarningDB()
        result = []
        for p in parties:
            pname = p.get("name", "")
            signals = db.get_signals_summary(pname, limit=10)
            result.append({
                "name": pname,
                "industry": p.get("industry", ""),
                "parent": p.get("parent", ""),
                "signals": signals,
                "signal_count": len(signals),
            })

        return result

    @staticmethod
    def _validate_and_enrich(data: WeeklyData) -> WeeklyData:
        """校验并补全 WeeklyData 缺失字段，打日志便于运维排查。

        - str 字段：空串或 "0" → FIELD_DEFAULTS 默认值
        - Optional[List] 字段：None → []
        - Optional[Dict] 字段：None → {"status": "unavailable"}
        - risk dict：确保 red/orange/yellow/total 键存在
        """
        # str 字段
        for field in ("loan_amount", "industry", "enterprise"):
            val = data.get(field, "")
            if not val or val == "0":
                default = FIELD_DEFAULTS.get(field, "未披露")
                logger.warning(
                    "WeeklyData field '{}' is empty, using default: {}",
                    field, default,
                )
                data[field] = default

        # Optional[List] 字段
        for field in ("party_a_signals", "warnings_signals"):
            if data.get(field) is None:
                logger.info(
                    "WeeklyData field '{}' is None, setting to []", field
                )
                data[field] = []

        # Optional[Dict] 字段
        for field in ("headcount_trend", "industry_data"):
            if data.get(field) is None:
                logger.warning(
                    "WeeklyData field '{}' is None, setting to {{'status': 'unavailable'}}",
                    field,
                )
                data[field] = {"status": "unavailable"}

        # risk dict 键完整性
        risk = data.get("risk", {})
        for key in ("red", "orange", "yellow", "total"):
            if key not in risk:
                risk[key] = 0
        data["risk"] = risk

        return data

    # ── 周报结构化数据构建（T3: dict 模式） ─────────────────

    def _build_weekly_data(self, topic: str, tasks: list) -> WeeklyData:
        """构建周报结构化数据字典。每个信号是 dict 的一个键，新增信号只需增加一个键值对。"""
        today = date.today()
        p_end = today.isoformat()
        p_start = (
            today.replace(day=1).isoformat()
            if today.day <= 7
            else today.replace(day=today.day - 7).isoformat()
        )
        enterprise = self._extract_enterprise_from_topic(topic)
        task_risk = self._calc_risk_counts_from_tasks(tasks)
        ref_text = self._read_reference_doc(enterprise)

        # 从 SQLite 读取已有预警数据（企查查+同花顺+票交所）
        db_warnings = self._read_warnings_from_db(enterprise)
        # 合并风险计数：SQLite 结构化数据优先，task 关键词扫描补充
        db_counts = db_warnings.get("counts", {})
        risk = {
            "red": max(task_risk.get("red", 0), db_counts.get("red", 0)),
            "orange": max(task_risk.get("orange", 0), db_counts.get("orange", 0)),
            "yellow": max(task_risk.get("yellow", 0), db_counts.get("yellow", 0)),
            "total": max(task_risk.get("total", 0), db_warnings.get("total", 0)),
        }

        # 企业字段: ChromaDB RAG → enterprises.yaml lookup → 空字符串
        industry = (self._rag_match("industry", ref_text, enterprise)
                    or self._get_enterprise_field(enterprise, "industry"))
        loan_amount = (self._rag_match("loan_amount", ref_text, enterprise)
                       or self._get_enterprise_field(enterprise, "loan_amount"))

        # ── 运营信号 ──
        headcount_trend = self._compute_headcount_trend(enterprise)

        # 关键时刻截图（含 snapshot_path 的原始记录）
        raw_snapshots = ReportingService._read_camera_snapshots(enterprise, weeks=4)
        key_snaps = [s for s in raw_snapshots if s.get("snapshot_path")]

        # Party A 运营信号（从 enterprises.yaml + warning_db 拉取）
        try:
            party_a_signals = self._fetch_party_a_signals(enterprise)
        except Exception as _exc:
            logger.warning("_fetch_party_a_signals failed for {}: {}", enterprise, _exc)
            party_a_signals = []

        # 提取供应链相关行业（甲方所在行业，去重）
        related_industries: list[str] = []
        for p in party_a_signals:
            p_ind = p.get("industry", "")
            if p_ind and p_ind != industry:
                related_industries.append(p_ind)
        # 去重保序
        seen_ind: set[str] = set()
        related_industries = [i for i in related_industries if not (i in seen_ind or seen_ind.add(i))]  # type: ignore[arg-type]

        # ── 行业宏观数据（三层百度搜索：宏观大盘+主体行业+供应链）──
        industry_data = self._fetch_industry_data(industry, related_industries)

        # 构建 WeeklyData 并通过校验层补全缺失字段
        data = WeeklyData(
            enterprise=enterprise,
            industry=industry,
            loan_amount=loan_amount,
            report_date=today.strftime("%Y-%m-%d"),
            report_period_start=p_start,
            report_period_end=p_end,
            ref_text=ref_text,
            risk=risk,
            warnings_signals=db_warnings.get("signals", []),
            warnings_summary=db_warnings,
            headcount_trend=headcount_trend,
            key_snapshots=key_snaps if key_snaps else None,
            camera_aggregated=raw_snapshots,  # 完整聚合数据，供 _build_video_inspection_section 使用
            party_a_signals=party_a_signals,
            industry_data=industry_data,
        )
        return self._validate_and_enrich(data)

    @staticmethod
    def _format_weekly_context(data: WeeklyData) -> str:
        """将 WeeklyData dict 格式化为 LLM 可解析的结构化上下文字符串。

        每个字段独立格式化；缺失字段优雅降级而不是崩溃。
        新增信号字段时只需在此方法中增加一个格式化块。
        """
        enterprise = data.get("enterprise", "未知")
        industry = data.get("industry", "未知")
        loan_amount = data.get("loan_amount", "未知")
        loan_display = loan_amount if loan_amount and loan_amount not in ("0", "未披露") else "未披露"
        report_date = data.get("report_date", date.today().isoformat())
        p_start = data.get("report_period_start", "")
        p_end = data.get("report_period_end", "")
        ref_text = data.get("ref_text", "")
        risk = data.get("risk", {"red": 0, "orange": 0, "yellow": 0, "total": 0})
        headcount_trend = data.get("headcount_trend")
        party_a_signals = data.get("party_a_signals")

        ctx = f"""【报告时间】
报告日期：{report_date}
报告周期：{p_start} ~ {p_end}

【企业信息】（来源：参考文档 / 默认值）
企业名称：{enterprise}
所属行业：{industry}
发放金额：{loan_display} 万元
"""
        if ref_text:
            ctx += f"\n【参考文档】\n{ref_text}\n"

        ctx += f"""\n【风险统计数据】
红色预警：{risk['red']} 项
橙色预警：{risk['orange']} 项
黄色预警：{risk['yellow']} 项
合计：{risk['total']} 项
"""

        # ── 预警信号明细（从 SQLite warning_log 读取）──
        warnings_signals = data.get("warnings_signals", [])
        if warnings_signals:
            ctx += "\n【历史预警信号】（来源：企查查/同花顺/百度/票交所，以下为系统已采集的真实数据，请直接引用，不要写\"无相关内容\"）\n"
            for s in warnings_signals[:15]:
                sev = s.get("severity", "?")
                sev_label = {"red": "🔴红", "orange": "🟠橙", "yellow": "🟡黄"}.get(sev, "⚪")
                title = s.get("title", "")
                detail = s.get("detail", "")
                text = detail if detail and detail != title else title
                ctx += f"{sev_label}级 | {text[:200]}\n"
            ctx += f"\n（以上共 {len(warnings_signals)} 条预警信号，均为系统实时采集的权威数据源信息）\n"
        else:
            ctx += "\n【历史预警信号】暂无历史预警数据\n"

        # ── 行业宏观数据（同花顺 iFinD，覆盖所有行业）──
        industry_data = data.get("industry_data")
        if industry_data:
            ctx += f"""
【行业宏观数据】（来源：{industry_data.get('source', '暂无')}）
行业名称：{industry_data.get('industry', '未知')}
行业状态：{industry_data.get('industry_status', '暂无数据')}
关键指标：{industry_data.get('key_indicators', '暂无行业指标数据')}
政策方向：{industry_data.get('policy_direction', '中性')}
政策详情：{industry_data.get('policy_detail', '暂无最新政策信息')}
风险提示：{industry_data.get('risk_warning', '未发现明显负面信号')}
"""
            events = industry_data.get("major_events", [])
            if events:
                ctx += "本周大事记：\n"
                for i, ev in enumerate(events[:5], 1):
                    ctx += f"  {i}. {ev}\n"
        else:
            ctx += """
【行业宏观数据】
行业状态：暂无数据
说明：行业宏观分析待获取，将使用默认行业概览
"""

        # ── 运营信号：视频巡检人数趋势 ──
        if headcount_trend and headcount_trend.get("status") != "insufficient":
            ctx += f"""
【视频巡检人数趋势】
趋势状态：{headcount_trend.get('status', 'unknown')}
本周日均人数：{headcount_trend.get('current_avg', 'N/A')}
前3周日均人数：{headcount_trend.get('prior_avg', 'N/A')}
变化幅度：{headcount_trend.get('delta_pct', 0) * 100:.1f}%
趋势说明：{headcount_trend.get('message', '')}
"""
        else:
            ctx += """
【视频巡检人数趋势】
趋势状态：insufficient
说明：数据不足，暂无法生成趋势
"""

        # ── 运营信号：甲方经营信号（T5 模板对应字段） ──
        if party_a_signals:
            ctx += "\n【甲方经营信号】（来源：企查查/百度舆情/同花顺）\n"
            ctx += "| 甲方名称 | 所属行业 | 预警信号数 | 最高风险等级 |\n"
            ctx += "|---------|---------|----------|------------|\n"
            for p in party_a_signals:
                name = p.get("name", "")
                industry = p.get("industry", "")
                count = p.get("signal_count", 0)
                signals = p.get("signals", [])
                sevs = [s.get("severity", "normal") for s in signals]
                max_sev = "🔴" if "red" in sevs else ("🟠" if "orange" in sevs else ("🟡" if "yellow" in sevs else "🟢"))
                ctx += f"| {name} | {industry} | {count} | {max_sev} |\n"
            # 注入甲方名称列表供 prompt 模板使用
            party_names = "、".join(p.get("name", "") for p in party_a_signals)
            ctx += f"\n（以上 {len(party_a_signals)} 家甲方核心企业的预警信号，请填入报告【二、核心企业监管】对应章节。甲方名称列表：{party_names}）\n"
        else:
            ctx += "\n【甲方经营信号】\n暂无甲方经营信号数据，后续将通过招标数据或工商变更频率补充。\n"

        return ctx

    # ── 主方法 ───────────────────────────────────────────────

    def generate_report(self, state: SummaryState) -> str:
        tasks_block = []
        notes_block = []
        for task in state.todo_items:
            tasks_block.append(
                f"### 任务 {task.id}: {task.title}\n"
                f"- 目标：{task.intent}\n- 查询：{task.query}\n"
                f"- 状态：{task.status}\n- 总结：\n{task.summary or '暂无'}\n"
                f"- 来源：\n{task.sources_summary or '暂无'}\n"
            )
            if self._notes and task.note_id:
                body = self._notes.read(task.note_id)
                if body:
                    notes_block.append(f"#### 笔记 {task.note_id}\n{body[:4000]}\n")

        if self._style == "weekly":
            system_prompt = weekly_report_writer_instructions.strip()
            weekly_data = self._build_weekly_data(
                state.research_topic, state.todo_items
            )
            weekly_ctx = self._format_weekly_context(weekly_data)
            sources = self._collect_sources(state.todo_items)
            prompt = (
                f"调查主题：{state.research_topic}\n\n"
                f"任务与总结：\n{''.join(tasks_block)}\n"
                f"\n结构化数据：\n{weekly_ctx}\n"
                f"\n参考来源：\n{sources}\n"
            )
            # 企查查原始数据注入
            for t in state.todo_items:
                if t.id == 5 and t.summary and t.status == "completed":
                    prompt += "\n【企查查原始数据】\n" + t.summary + "\n"
                    break
            if notes_block:
                prompt += f"\n任务笔记摘录：\n{''.join(notes_block)}\n"
            prompt += "\n请整合以上搜索任务总结、结构化数据和参考来源，严格按贷后监管综合周报模板生成报告。"
        else:
            system_prompt = report_writer_instructions.strip()
            prompt = (
                f"调查主题：{state.research_topic}\n\n"
                f"任务与总结：\n{''.join(tasks_block)}\n"
            )
            if notes_block:
                prompt += f"\n任务笔记摘录：\n{''.join(notes_block)}\n"
            prompt += "\n请整合以上信息，撰写结构完整的中文 Markdown 调查报告。"

        try:
            response = invoke_llm(self._config, system_prompt, prompt)
            report_text = response.strip()
        except Exception as _llm_err:
            logger.warning(
                "LLM 调用失败，降级为结构化报告: {}",
                _llm_err,
            )
            if self._style == "weekly":
                report_text = self._build_fallback_report(weekly_data, state)
            else:
                report_text = f"报告生成失败，LLM 服务不可用。\n\n错误: {_llm_err}"

        if self._config.strip_thinking_tokens:
            report_text = strip_thinking_tokens(report_text)
        report_text = strip_tool_calls(report_text).strip() or "报告生成失败，请检查输入。"

        # 后处理：用代码生成的视频巡检章节替换占位标记
        if self._style == "weekly":
            _aggregated = weekly_data.get("camera_aggregated") or []
            _key_snaps = weekly_data.get("key_snapshots") or []
            _trend = weekly_data.get("headcount_trend")
            video_section = ReportingService._build_video_inspection_section(
                _aggregated, _key_snaps, _trend
            )
            if "<!-- VIDEO_INSPECTION_PLACEHOLDER -->" in report_text:
                report_text = report_text.replace(
                    "<!-- VIDEO_INSPECTION_PLACEHOLDER -->", video_section
                )
            else:
                # 降级：LLM 未输出占位标记（极端情况），追加到末尾
                logger.warning("报告中未找到 VIDEO_INSPECTION_PLACEHOLDER，追加到末尾")
                report_text += "\n" + video_section

        # 兜底：无条件清理 LLM 可能照搬旧模板生成的 localhost:5000 URL
        report_text = re.sub(
            r"http://localhost:5000/snapshots/",
            "/snapshots/",
            report_text,
        )

        return report_text

    def _build_fallback_report(
        self, weekly_data: WeeklyData, state: SummaryState
    ) -> str:
        """LLM 不可用时，用结构化数据直接组装基础周报。

        保留所有数据：企业信息、风险统计、视频巡检趋势、截图、搜索任务总结。
        """
        wd = weekly_data
        lines = []
        lines.append("# 贷后监管综合周报")
        lines.append("")
        lines.append(
            f"报告日期：{wd.get('report_date', '')}　"
            f"报告周期：{wd.get('report_period_start', '')} ~ {wd.get('report_period_end', '')}"
        )
        lines.append(
            f"监管企业：{wd.get('enterprise', '')}　|　"
            f"所属行业：{wd.get('industry', '')}　|　"
            f"发放金额：{wd.get('loan_amount', '')}万元　|　"
            f"报告类型：贷后监管综合周报"
        )
        lines.append("")
        lines.append("> ⚠️ [系统备注] LLM 服务暂时不可用，本报告由结构化数据自动组装。内容不含 AI 分析，仅展示原始数据。")
        lines.append("")
        lines.append("---")
        lines.append("")

        # 一、风险统计
        risk = wd.get("risk", {})
        lines.append("## 一、风险统计数据")
        lines.append("")
        lines.append(f"- 红色预警：{risk.get('red', 0)} 项")
        lines.append(f"- 橙色预警：{risk.get('orange', 0)} 项")
        lines.append(f"- 黄色预警：{risk.get('yellow', 0)} 项")
        lines.append(f"- 合计：{risk.get('total', 0)} 项")
        lines.append("")

        # 二、搜索任务总结
        lines.append("## 二、搜索任务总结")
        lines.append("")
        for t in state.todo_items:
            if t.status == "completed" and t.summary:
                lines.append(f"### {t.title}")
                lines.append(f"{t.summary[:2000]}")
                lines.append("")
        if not any(t.status == "completed" and t.summary for t in state.todo_items):
            lines.append("暂无搜索任务结果。")
            lines.append("")

        # 三、视频巡检（由代码从数据库数据生成）
        _aggregated = wd.get("camera_aggregated") or []
        _key_snaps = wd.get("key_snapshots") or []
        _trend = wd.get("headcount_trend")
        video_section = ReportingService._build_video_inspection_section(
            _aggregated, _key_snaps, _trend
        )
        # fallback report 使用不同的章节编号，将"## 四"修正为"## 三"
        video_section = video_section.replace("## 四、现场视频巡检", "## 三、现场视频巡检")
        lines.append(video_section)

        # 四、甲方经营信号
        lines.append("## 四、甲方经营信号")
        lines.append("")
        party_a = wd.get("party_a_signals") or []
        if party_a:
            for p in party_a:
                name = p.get("name", "")
                count = p.get("signal_count", 0)
                signals = p.get("signals", [])
                sevs = [s.get("severity", "normal") for s in signals]
                max_sev = "🔴红" if "red" in sevs else ("🟠橙" if "orange" in sevs else ("🟡黄" if "yellow" in sevs else "🟢正常"))
                lines.append(f"- {name}（{p.get('industry', '')}）：{count} 条预警，最高风险 {max_sev}")
        else:
            lines.append("暂无甲方经营信号数据，后续将通过招标数据或工商变更频率补充。")
        lines.append("")

        # 参考来源
        lines.append("---")
        lines.append("")
        lines.append("— 本报告由贷后监管系统自动生成（降级模式），需经人工确认后方可作为正式依据 —")
        lines.append(f"报告出具方：贷后监管综合报告系统　|　生成时间：{wd.get('report_date', '')}")

        return "\n".join(lines)


# ── 行业数据辅助函数 ──────────────────────────────────


def _summarize_industry_indicators(
    industry_result: Dict[str, Any],
    macro_result: Dict[str, Any],
) -> str:
    """从同花顺 API 返回中提取行业关键指标摘要。"""
    parts: List[str] = []

    macro = macro_result.get("data", {})
    tables = macro.get("tables", [])
    for table in tables:
        rows = table.get("table", [])
        if rows:
            last = rows[-1]
            for k, v in last.items():
                try:
                    parts.append(f"{k}: {float(v):.2f}")
                except (ValueError, TypeError):
                    parts.append(f"{k}: {v}")

    industry = industry_result.get("industry_specific", {})
    ind_tables = industry.get("tables", [])
    for table in ind_tables:
        rows = table.get("table", [])
        if rows:
            for k, v in rows[-1].items():
                parts.append(f"行业{k}: {v}")

    return "; ".join(parts) if parts else "暂无行业指标数据"


def _extract_industry_events(industry_result: Dict[str, Any]) -> List[str]:
    """提取行业大事记。"""
    events: List[str] = []
    reports = industry_result.get("reports", {})
    tables = reports.get("tables", [])
    for table in tables:
        rows = table.get("table", [])
        for row in rows[:5]:
            title = row.get("title") or row.get("report_title", "")
            if title:
                events.append(str(title))
    return events


def _summarize_industry_signals(signals: List[Dict[str, str]]) -> str:
    """汇总行业预警信号为风险提示文本。"""
    if not signals:
        return "未发现明显负面信号。"
    red = [s for s in signals if s.get("severity") == "red"]
    orange = [s for s in signals if s.get("severity") == "orange"]
    yellow = [s for s in signals if s.get("severity") == "yellow"]
    parts = []
    if red:
        parts.append(f"{len(red)} 项严重信号")
    if orange:
        parts.append(f"{len(orange)} 项预警信号")
    if yellow:
        parts.append(f"{len(yellow)} 项关注信号")
    total = len(red) + len(orange) + len(yellow)
    return f"监测到 {total} 条行业风险信号。" + " ".join(parts) if parts else "未发现明显负面信号。"
