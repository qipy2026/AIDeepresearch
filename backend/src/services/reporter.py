"""最终报告（LangChain LLM），支持标准报告和贷后周报两种模式。"""

from __future__ import annotations

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
    def _read_camera_snapshots(enterprise: str, weeks: int = 4) -> List[Dict[str, Any]]:
        """读取企业指定周数内的摄像头快照人数数据。

        当前为 stub 实现——CameraSnapshot 表尚未在代码层建模。
        返回空列表使 _compute_headcount_trend 输出"数据不足"，
        直到真实数据管道（摄像头 → AI → DB）完成迁移。
        """
        # TODO: 替换为真实 DB 查询
        # SELECT snapshot_date, headcount FROM camera_snapshots
        # WHERE enterprise_name = ? AND snapshot_date >= date('now', f'-{weeks*7} days')
        # ORDER BY snapshot_date DESC
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
        from services.rag_store import query as rag_query

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
    def _fetch_industry_data(industry: str, enterprise: str = "") -> Dict[str, Any]:
        """从同花顺 iFinD 获取行业宏观数据。

        覆盖所有行业，不限于债务企业或核心监管企业所在行业。
        API 不可用时优雅降级返回占位数据。
        """
        try:
            from services.ths_client import create_client
            client = create_client()
            industry_result = client.get_industry_data(industry_name=industry)
            macro_result = client.get_macro_data()

            signals = industry_result.get("signals", [])
            return {
                "industry": industry,
                "industry_status": "正常" if industry_result.get("macro") else "暂无数据",
                "key_indicators": _summarize_industry_indicators(
                    industry_result, macro_result
                ),
                "major_events": _extract_industry_events(industry_result),
                "policy_direction": "中性",
                "policy_detail": "暂无最新政策信息",
                "risk_warning": _summarize_industry_signals(signals),
                "signals": signals,
                "source": "同花顺 iFinD",
                "macro_available": bool(macro_result.get("data")),
                "industry_available": bool(industry_result.get("industry_specific")),
            }
        except Exception as e:
            logger.warning(f"行业数据获取失败 ({industry}): {e}")
            return {
                "industry": industry,
                "industry_status": "暂无数据",
                "key_indicators": f"行业数据分析待获取（{industry}行业）",
                "major_events": [],
                "policy_direction": "中性",
                "policy_detail": "暂无最新政策信息",
                "risk_warning": "未发现明显负面信号",
                "signals": [],
                "source": "暂无",
                "macro_available": False,
                "industry_available": False,
            }

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

        # Party A 运营信号（条件性）
        party_a_signals: Optional[List[Dict[str, Any]]] = None

        # ── 行业宏观数据（同花顺 iFinD，覆盖所有行业）──
        industry_data = self._fetch_industry_data(industry, enterprise)

        return WeeklyData(
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
            party_a_signals=party_a_signals,
            industry_data=industry_data,
        )

    @staticmethod
    def _format_weekly_context(data: WeeklyData) -> str:
        """将 WeeklyData dict 格式化为 LLM 可解析的结构化上下文字符串。

        每个字段独立格式化；缺失字段优雅降级而不是崩溃。
        新增信号字段时只需在此方法中增加一个格式化块。
        """
        enterprise = data.get("enterprise", "未知")
        industry = data.get("industry", "未知")
        loan_amount = data.get("loan_amount", "未知")
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
发放金额：{loan_amount} 万元
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
            ctx += "\n【历史预警信号】（来源：企查查/同花顺/百度/票交所）\n"
            for s in warnings_signals[:10]:
                sev_label = {"red": "🔴", "orange": "🟠", "yellow": "🟡"}.get(s.get("severity", ""), "⚪")
                ctx += f"{sev_label} [{s.get('severity','?')}] {s.get('title','')}"
                detail = s.get("detail", "")
                if detail and detail != s.get("title", ""):
                    ctx += f" — {detail[:120]}"
                ctx += "\n"
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

        # ── 运营信号：视频巡检人数趋势（T4 模板对应字段） ──
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
            ctx += "\n【甲方经营信号】\n"
            for sig in party_a_signals:
                ctx += f"- {sig.get('name', '')}: {sig.get('value', '')} ({sig.get('status', '')})\n"
        else:
            ctx += "\n【甲方经营信号】\n无相关内容\n"

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

        response = invoke_llm(self._config, system_prompt, prompt)
        report_text = response.strip()
        if self._config.strip_thinking_tokens:
            report_text = strip_thinking_tokens(report_text)
        return strip_tool_calls(report_text).strip() or "报告生成失败，请检查输入。"


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
