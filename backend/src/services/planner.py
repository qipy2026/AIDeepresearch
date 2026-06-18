"""调查任务规划（LangChain LLM）。"""

from __future__ import annotations

import json
import logging
import re
from typing import Any, List, Optional

from config import Configuration
from core.llm import invoke_llm
from models import SummaryState, TodoItem
from prompts import get_current_date, todo_planner_instructions, todo_planner_system_prompt
from utils import strip_thinking_tokens

logger = logging.getLogger(__name__)

TOOL_CALL_PATTERN = re.compile(
    r"\[TOOL_CALL:(?P<tool>[^:]+):(?P<body>[^\]]+)\]",
    re.IGNORECASE,
)


class PlanningService:
    def __init__(self, config: Configuration) -> None:
        self._config = config
        self._system = todo_planner_system_prompt.strip()

    def plan_todo_list(self, state: SummaryState) -> List[TodoItem]:
        prompt = todo_planner_instructions.format(
            current_date=get_current_date(),
            research_topic=state.research_topic,
        )
        response = invoke_llm(self._config, self._system, prompt)
        logger.info("Planner raw output (truncated): %s", response[:500])

        tasks_payload = self._extract_tasks(response)
        todo_items: List[TodoItem] = []
        for idx, item in enumerate(tasks_payload, start=1):
            title = str(item.get("title") or f"任务{idx}").strip()
            intent = str(item.get("intent") or "聚焦主题的关键问题").strip()
            query = str(item.get("query") or state.research_topic).strip() or state.research_topic
            todo_items.append(
                TodoItem(id=idx, title=title, intent=intent, query=query)
            )
        state.todo_items = todo_items
        return todo_items

    @staticmethod
    def create_fallback_task(state: SummaryState) -> TodoItem:
        return TodoItem(
            id=1,
            title="基础背景梳理",
            intent="收集主题的核心背景与最新动态",
            query=f"{state.research_topic} 最新进展"
            if state.research_topic
            else "基础背景梳理",
        )

    def _extract_tasks(self, raw_response: str) -> List[dict[str, Any]]:
        text = raw_response.strip()
        if self._config.strip_thinking_tokens:
            text = strip_thinking_tokens(text)
        json_payload = self._extract_json_payload(text)
        tasks: List[dict[str, Any]] = []
        if isinstance(json_payload, dict):
            candidate = json_payload.get("tasks")
            if isinstance(candidate, list):
                tasks.extend(i for i in candidate if isinstance(i, dict))
        elif isinstance(json_payload, list):
            tasks.extend(i for i in json_payload if isinstance(i, dict))
        return tasks

    def _extract_json_payload(self, text: str) -> Optional[dict[str, Any] | list]:
        start, end = text.find("{"), text.rfind("}")
        if start != -1 and end > start:
            try:
                return json.loads(text[start : end + 1])
            except json.JSONDecodeError:
                pass
        start, end = text.find("["), text.rfind("]")
        if start != -1 and end > start:
            try:
                return json.loads(text[start : end + 1])
            except json.JSONDecodeError:
                return None
        return None
