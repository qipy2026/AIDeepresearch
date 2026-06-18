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
        return {"state": SummaryState(research_topic=data["topic"])}

    def plan(data: ResearchGraphState) -> dict:
        st = data["state"]
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
