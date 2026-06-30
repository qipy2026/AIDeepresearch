"""LangGraph 贷后管理工作流：规划 → 串行执行任务 → 撰写报告。"""

from __future__ import annotations

from typing import Any, TypedDict

from langgraph.graph import END, StateGraph

from config import Configuration
from models import SummaryState, SummaryStateOutput, TodoItem


class ResearchGraphState(TypedDict, total=False):
    topic: str
    state: SummaryState
    report: str
    output: SummaryStateOutput


def _check_and_collect(topic: str):
    """周报模式：检查目标企业预警数据新鲜度，不足时触发采集。"""
    import logging
    _logger = logging.getLogger(__name__)
    try:
        from services.reporter import ReportingService
        from warning_db import WarningDB
        _ent = ReportingService._extract_enterprise_from_topic(topic)
        _db = WarningDB()
        _recent = _db.count_recent_warnings(_ent, hours=24)
        if _recent < 5:
            _logger.info("预警数据不足(%s近24h仅%d条)，触发自动采集", _ent, _recent)
            try:
                from main import _warning_collect_cycle
                _warning_collect_cycle()
            except Exception:
                pass
    except Exception:
        pass


def run_research_graph(agent: Any, topic: str) -> SummaryStateOutput:
    """同步全流程（流式接口仍走 agent.run_stream 的并行实现）。"""
    graph = _build_graph(agent)
    result = graph.invoke({"topic": topic})
    out = result.get("output")
    if out is None:
        raise RuntimeError("调查流程未返回结果")
    return out


def _build_graph(agent: Any):
    workflow = StateGraph(ResearchGraphState)

    def init_state(data: ResearchGraphState) -> dict:
        topic = data["topic"]
        # 周报模式：检查预警数据新鲜度，不足时先采集
        if getattr(agent.reporting, '_style', None) == 'weekly':
            _check_and_collect(topic)
        return {"state": SummaryState(research_topic=topic)}

    def plan(data: ResearchGraphState) -> dict:
        st = data["state"]
        # 周报模式使用固定 5 任务管线（和 stream 路径一致）
        if getattr(agent.reporting, '_style', None) == 'weekly':
            st.todo_items = agent._make_weekly_tasks(st.research_topic)
        else:
            st.todo_items = agent.planner.plan_todo_list(st)
        if not st.todo_items:
            st.todo_items = [agent.planner.create_fallback_task(st)]
        return {"state": st}

    def run_tasks(data: ResearchGraphState) -> dict:
        st = data["state"]
        for task in st.todo_items:
            for _ in agent._execute_task(st, task, emit_stream=False):
                pass
        return {"state": st}

    def write_report(data: ResearchGraphState) -> dict:
        st = data["state"]
        report = agent.reporting.generate_report(st)
        st.structured_report = report
        st.running_summary = report
        agent._persist_final_report(st, report)
        output = SummaryStateOutput(
            running_summary=report,
            report_markdown=report,
            todo_items=st.todo_items,
        )
        return {"state": st, "report": report, "output": output}

    workflow.add_node("init", init_state)
    workflow.add_node("plan", plan)
    workflow.add_node("tasks", run_tasks)
    workflow.add_node("report", write_report)
    workflow.set_entry_point("init")
    workflow.add_edge("init", "plan")
    workflow.add_edge("plan", "tasks")
    workflow.add_edge("tasks", "report")
    workflow.add_edge("report", END)
    return workflow.compile()
