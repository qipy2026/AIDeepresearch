"""贷后管理编排（LangGraph + LangChain，已脱离 hello_agents）。"""

from __future__ import annotations

import logging
import sys
from pathlib import Path
from queue import Empty, Queue
from threading import Lock, Thread
from typing import Any, Callable, Iterator

if sys.platform == "win32":
    for _stream in (sys.stdout, sys.stderr):
        if hasattr(_stream, "reconfigure"):
            try:
                _stream.reconfigure(encoding="utf-8", errors="replace")
            except Exception:
                pass

from config import Configuration
from graph.research_graph import run_research_graph
from models import SummaryState, SummaryStateOutput, TodoItem
from services.planner import PlanningService
from services.reporter import ReportingService
from services.search import dispatch_search, prepare_research_context
from services.summarizer import SummarizationService
from services.notes_store import NotesStore
from services.tool_events import ToolCallTracker

logger = logging.getLogger(__name__)


class DeepResearchAgent:
    """规划 → 搜索 → 总结 → 报告（LangGraph 同步路径 + 多线程流式路径）。"""

    def __init__(self, config: Configuration | None = None) -> None:
        self.config = config or Configuration.from_env()
        self.notes: NotesStore | None = None
        if self.config.enable_notes:
            self.notes = NotesStore(self.config.notes_workspace)

        self.planner = PlanningService(self.config)
        self.summarizer = SummarizationService(self.config)
        self.reporting = ReportingService(self.config, self.notes, report_style="weekly")

        self._tool_tracker = ToolCallTracker(
            self.config.notes_workspace if self.config.enable_notes else None
        )
        self._tool_event_sink_enabled = False
        self._state_lock = Lock()
        self._last_search_notices: list[str] = []

    def run(self, topic: str) -> SummaryStateOutput:
        if getattr(self.reporting, '_style', None) == 'weekly':
            return run_research_graph(self, topic)
        return run_research_graph(self, topic)

    @staticmethod
    def _make_weekly_tasks(topic: str) -> list[TodoItem]:
        from services.reporter import ReportingService
        enterprise = ReportingService._extract_enterprise_from_topic(topic)
        industry = ReportingService._get_enterprise_field(enterprise, "industry") or "行业"

        # 获取该企业的甲方列表（从 enterprises.yaml）
        ents = ReportingService._load_enterprises_yaml()
        parties = [e for e in ents if e.get("debtor") == enterprise and e.get("role") == "甲方"]

        # ── 行业搜索 query（百度优化）──
        industry_queries = [
            f"{industry} 行业 发展 规模 2026",
            f"{industry} 监管 政策 新规 2026",
            f"{industry} 行业 风险 挑战 新闻",
            f"{industry} 市场 趋势 分析",
        ]

        # ── 供应链(甲方)搜索 query（百度优化）──
        supply_queries = []
        for p in parties[:4]:
            pname = p.get("name", "")
            pparent = p.get("parent", "")
            if pname:
                supply_queries.append(f"{pname} 经营 风险 诉讼")
                supply_queries.append(f"{pname} 项目 动态 处罚 新闻")
            if pparent:
                supply_queries.append(f"{pparent} 经营 风险 动态")
        if not supply_queries:
            supply_queries = ["核心企业 风险 排查"]

        # ── 债务方搜索 query（百度优化）──
        debtor_queries = [
            f"{enterprise} 工商 变更 信息",
            f"{enterprise} 法律 诉讼 裁判 文书",
            f"{enterprise} 经营 异常 处罚 新闻",
            f"{enterprise} 财务 状况 风险",
        ]

        return [
            TodoItem(id=1, title="行业与宏观监管",
                     intent="搜索行业动态、政策变化和风险提示",
                     query=f"{industry} 行业 发展 2026",
                     micro_queries=industry_queries),
            TodoItem(id=2, title="核心企业监管（供应链扫描）",
                     intent="排查甲方核心企业的经营风险、诉讼、舆情",
                     query="核心企业 风险 排查" if not supply_queries else supply_queries[0],
                     micro_queries=supply_queries),
            TodoItem(id=3, title="债务企业自身监管",
                     intent="排查企业工商、诉讼、经营异常、财务风险信息",
                     query=debtor_queries[0],
                     micro_queries=debtor_queries),
            TodoItem(id=4, title="现场视频巡检",
                     intent="巡检数据",
                     query=f"{enterprise} 监控",
                     micro_queries=[]),
            TodoItem(id=5, title="企查查数据查询",
                     intent="通过企查查查询甲乙方工商、风险、经营数据",
                     query="企查查 企业查询",
                     micro_queries=(
                         [p.get("name", "") for p in parties if p.get("name")] +
                         [enterprise]
                     )),
        ]

    def run_stream(self, topic: str) -> Iterator[dict[str, Any]]:
        state = SummaryState(research_topic=topic)
        yield {"type": "status", "message": "初始化调查流程（LangGraph 流式管线）"}

        # 检查预警数据新鲜度：不足时先触发采集
        if getattr(self.reporting, '_style', None) == 'weekly':
            from services.reporter import ReportingService
            from warning_db import WarningDB
            _ent = ReportingService._extract_enterprise_from_topic(topic)
            _db = WarningDB()
            _recent = _db.count_recent_warnings(_ent, hours=24)
            _total = _db.count_recent_warnings(_ent, hours=720)  # 30 days
            if _recent < 5 and _total < 20:
                yield {"type": "status", "message": f"预警数据不足（近24h仅有{_recent}条），正在自动采集…"}
                try:
                    # 触发采集：尝试调用 APScheduler 的 collect job
                    try:
                        from apscheduler.schedulers.background import BackgroundScheduler
                        import main as _main
                        # 通过 main 的 scheduler 强制执行一次
                        _app = getattr(_main, 'app', None)
                        if _app and hasattr(_app, '_warning_collect'):
                            _app._warning_collect()
                    except Exception:
                        pass  # 采集非关键路径，失败不阻塞报告生成
                    yield {"type": "status", "message": "采集完成，继续生成报告"}
                except Exception as _e:
                    yield {"type": "status", "message": f"采集出错: {_e}，使用现有数据继续"}

        if getattr(self.reporting, '_style', None) == 'weekly':
            state.todo_items = self._make_weekly_tasks(topic)
        else:
            state.todo_items = self.planner.plan_todo_list(state)
        if not state.todo_items:
            state.todo_items = [self.planner.create_fallback_task(state)]

        channel_map: dict[int, dict[str, Any]] = {}
        for index, task in enumerate(state.todo_items, start=1):
            token = f"task_{task.id}"
            task.stream_token = token
            channel_map[task.id] = {"step": index, "token": token}

        yield {
            "type": "todo_list",
            "tasks": [self._serialize_task(t) for t in state.todo_items],
            "step": 0,
        }

        event_queue: Queue[dict[str, Any]] = Queue()

        def enqueue(
            event: dict[str, Any],
            *,
            task: TodoItem | None = None,
            step_override: int | None = None,
        ) -> None:
            payload = dict(event)
            if task is not None:
                payload["task_id"] = task.id
            tid = payload.get("task_id")
            channel = channel_map.get(tid) if tid is not None else None
            if channel:
                payload.setdefault("step", channel["step"])
                payload["stream_token"] = channel["token"]
            if step_override is not None:
                payload["step"] = step_override
            event_queue.put(payload)

        threads: list[Thread] = []

        def worker(task: TodoItem, step: int) -> None:
            try:
                enqueue(
                    {
                        "type": "task_status",
                        "task_id": task.id,
                        "status": "in_progress",
                        "title": task.title,
                        "intent": task.intent,
                    },
                    task=task,
                )
                for event in self._execute_task(state, task, emit_stream=True, step=step):
                    enqueue(event, task=task)
            except Exception as exc:
                logger.exception("Task failed", exc_info=exc)
                enqueue(
                    {
                        "type": "task_status",
                        "task_id": task.id,
                        "status": "failed",
                        "detail": str(exc),
                        "title": task.title,
                    },
                    task=task,
                )
            finally:
                enqueue({"type": "__task_done__", "task_id": task.id})

        for task in state.todo_items:
            step = channel_map.get(task.id, {}).get("step", 0)
            t = Thread(target=worker, args=(task, step), daemon=True)
            threads.append(t)
            t.start()

        finished = 0
        total = len(state.todo_items)
        try:
            while finished < total:
                ev = event_queue.get()
                if ev.get("type") == "__task_done__":
                    finished += 1
                    continue
                yield ev
            while True:
                try:
                    ev = event_queue.get_nowait()
                except Empty:
                    break
                if ev.get("type") != "__task_done__":
                    yield ev
        finally:
            for t in threads:
                t.join()

        yield {"type": "generating_report", "message": "正在生成最终报告，请稍候..."}
        report = self.reporting.generate_report(state)
        state.structured_report = report
        state.running_summary = report
        note_event = self._persist_final_report(state, report)
        if note_event:
            yield note_event
        yield {
            "type": "final_report",
            "report": report,
            "note_id": state.report_note_id,
            "note_path": state.report_note_path,
        }
        yield {"type": "done"}

    def _execute_task(
        self,
        state: SummaryState,
        task: TodoItem,
        *,
        emit_stream: bool,
        step: int | None = None,
    ) -> Iterator[dict[str, Any]]:
        task.status = "in_progress"

        # ── 企查查 MCP 任务（独立第 5 路并行） ──
        if task.id == 5:
            from services.qichacha_mcp import query_risk_scan, query_judicial_documents, query_bidding, query_news
            parts: list[str] = []
            for ent_name in (task.micro_queries or []):
                if not ent_name.strip():
                    continue
                parts.append(f"【{ent_name}】")
                risk = query_risk_scan(ent_name)
                if risk:
                    parts.append(f"风险扫描：{risk}")
                jud = query_judicial_documents(ent_name)
                if jud:
                    parts.append(f"司法文书：{jud}")
                bid = query_bidding(ent_name)
                if bid:
                    parts.append(f"招投标：{bid}")
                news = query_news(ent_name)
                if news:
                    parts.append(f"新闻舆情：{news}")
            if parts:
                task.summary = "\n".join(parts)
                task.status = "completed"
                if emit_stream:
                    yield {
                        "type": "task_status",
                        "task_id": task.id,
                        "status": "completed",
                        "summary": task.summary,
                        "title": task.title,
                        "step": step,
                    }
            else:
                task.status = "skipped"
                if emit_stream:
                    yield {
                        "type": "task_status",
                        "task_id": task.id,
                        "status": "skipped",
                        "title": task.title,
                        "step": step,
                    }
            return

        # ── 微服务模式：遍历所有 query 合并结果 ──
        queries = task.micro_queries or [task.query]
        all_results: list[dict] = []
        all_notices: list[str] = []
        last_answer: str | None = None
        last_backend = "duckduckgo"

        for q in queries:
            if not q or not q.strip():
                continue
            # 从 topic 提取企业名，传给本地搜索做精确匹配
            from services.reporter import ReportingService
            _ent = ReportingService._extract_enterprise_from_topic(state.research_topic)
            search_result, notices, answer_text, backend = dispatch_search(
                q, self.config, state.research_loop_count, enterprise=_ent
            )
            if notices:
                all_notices.extend(n for n in notices if n)
            if search_result and search_result.get("results"):
                all_results.extend(search_result["results"])
                last_answer = answer_text or last_answer
                last_backend = backend

        task.notices = all_notices

        if all_notices and emit_stream:
            for notice in all_notices:
                if notice:
                    yield {
                        "type": "status",
                        "message": notice,
                        "task_id": task.id,
                        "step": step,
                    }

        if not all_results:
            # ── 搜索无结果 → RAG 回退 ──
            from services.rag_store import query as rag_query
            rag_text = rag_query(task.intent or task.title, "", n_results=3)
            if rag_text:
                task.summary = f"[参考文档] {rag_text[:500]}"
                task.status = "completed"
                task.sources_summary = "来源：向量库参考文档"
                if emit_stream:
                    yield {
                        "type": "task_status",
                        "task_id": task.id,
                        "status": "completed",
                        "summary": task.summary,
                        "title": task.title,
                        "step": step,
                    }
                return

            task.status = "skipped"
            if emit_stream:
                yield {
                    "type": "task_status",
                    "task_id": task.id,
                    "status": "skipped",
                    "title": task.title,
                    "step": step,
                }
            return

        merged_result: dict[str, Any] = {
            "results": all_results,
            "backend": last_backend,
            "answer": last_answer,
        }
        sources_summary, context = prepare_research_context(
            merged_result, last_answer, self.config
        )
        task.sources_summary = sources_summary
        with self._state_lock:
            state.web_research_results.append(context)
            state.sources_gathered.append(sources_summary)
            state.research_loop_count += 1

        summary_text: str | None = None
        if emit_stream:
            yield {
                "type": "sources",
                "task_id": task.id,
                "latest_sources": sources_summary,
                "raw_context": context,
                "step": step,
                "backend": backend,
            }
            stream, getter = self.summarizer.stream_task_summary(state, task, context)
            for chunk in stream:
                if chunk:
                    yield {
                        "type": "task_summary_chunk",
                        "task_id": task.id,
                        "content": chunk,
                        "step": step,
                    }
            summary_text = getter()
        else:
            summary_text = self.summarizer.summarize_task(state, task, context)

        task.summary = (summary_text or "").strip() or "暂无可用信息"
        task.status = "completed"

        if self.notes and task.summary:
            nid = self.notes.create(
                title=f"任务{task.id}：{task.title}",
                content=task.summary,
                note_type="task",
                tags=["deep_research", "task"],
            )
            task.note_id = nid
            task.note_path = str(Path(self.config.notes_workspace) / f"{nid}.md")

        if emit_stream:
            yield {
                "type": "task_status",
                "task_id": task.id,
                "status": "completed",
                "summary": task.summary,
                "sources_summary": task.sources_summary,
                "note_id": task.note_id,
                "note_path": task.note_path,
                "step": step,
            }

    def _drain_tool_events(
        self, state: SummaryState, *, step: int | None = None
    ) -> list[dict[str, Any]]:
        return self._tool_tracker.drain(state, step=step)

    def _serialize_task(self, task: TodoItem) -> dict[str, Any]:
        return {
            "id": task.id,
            "title": task.title,
            "intent": task.intent,
            "query": task.query,
            "status": task.status,
            "summary": task.summary,
            "sources_summary": task.sources_summary,
            "note_id": task.note_id,
            "note_path": task.note_path,
            "stream_token": task.stream_token,
        }

    def _persist_final_report(
        self, state: SummaryState, report: str
    ) -> dict[str, Any] | None:
        if not self.notes or not report.strip():
            return None
        title = f"调查报告：{state.research_topic}".strip() or "调查报告"
        note_id = self.notes.find_report_note_id(state.research_topic)
        if note_id:
            self.notes.update(note_id, report, title=title)
        else:
            note_id = self.notes.create(
                title=title,
                content=report,
                note_type="conclusion",
                tags=["deep_research", "report"],
            )
        state.report_note_id = note_id
        path = Path(self.config.notes_workspace) / f"{note_id}.md"
        state.report_note_path = str(path)
        return {
            "type": "report_note",
            "note_id": note_id,
            "title": title,
            "note_path": str(path),
        }


def run_deep_research(
    topic: str, config: Configuration | None = None
) -> SummaryStateOutput:
    return DeepResearchAgent(config=config).run(topic)
