"""最终报告（LangChain LLM），支持标准报告和贷后周报两种模式。"""

from __future__ import annotations

import re
from datetime import date, datetime
from pathlib import Path

from config import Configuration
from core.llm import invoke_llm
from models import SummaryState
from prompts import report_writer_instructions, weekly_report_writer_instructions
from services.notes_store import NotesStore
from services.text_processing import strip_tool_calls
from utils import strip_thinking_tokens


REFS_DIR = Path(__file__).resolve().parent.parent.parent / "references"


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

    # ── 周报辅助方法 ──────────────────────────────────────────

    @staticmethod
    def _extract_enterprise_from_topic(topic: str) -> str:
        """从调查主题中提取企业名。"""
        m = re.search(r'([一-鿿]{2,20}(?:有限公司|有限责任公司|分公司))', topic)
        return m.group(1) if m else topic.strip()

    @staticmethod
    def _calc_risk_counts_from_tasks(tasks: list) -> dict:
        """遍历所有任务搜索结果，统计负面关键词命中数生成风险计数。"""
        negative_kw = ["风险", "下降", "萎缩", "违约", "处罚", "下滑", "亏损"]
        total_hits = 0
        for t in tasks:
            text = f"{t.summary or ''} {t.sources_summary or ''}"
            total_hits += sum(1 for kw in negative_kw if kw in text)
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

    def _build_weekly_context(self, topic: str, tasks: list) -> str:
        """构建周报结构化上下文（模拟数据 + 参考文档 RAG）。"""
        today = date.today()
        p_end = today.isoformat()
        p_start = (
            today.replace(day=1).isoformat()
            if today.day <= 7
            else today.replace(day=today.day - 7).isoformat()
        )
        enterprise = self._extract_enterprise_from_topic(topic)
        risk = self._calc_risk_counts_from_tasks(tasks)
        ref_text = self._read_reference_doc(enterprise)
        industry = self._rag_match("industry", ref_text, enterprise) or "安保服务"
        loan_amount = self._rag_match("loan_amount", ref_text, enterprise) or "1000.0"

        ctx = f"""【报告时间】
报告日期：{today.strftime('%Y-%m-%d')}
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
            weekly_ctx = self._build_weekly_context(
                state.research_topic, state.todo_items
            )
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
