"""任务总结（LangChain LLM 流式/同步）。"""

from __future__ import annotations

from collections.abc import Callable, Iterator
from typing import Tuple

from config import Configuration
from core.llm import invoke_llm, stream_llm
from models import SummaryState, TodoItem
from prompts import task_summarizer_instructions
from services.notes import build_note_guidance
from services.text_processing import strip_tool_calls
from utils import strip_thinking_tokens


class SummarizationService:
    def __init__(self, config: Configuration) -> None:
        self._config = config
        self._system = task_summarizer_instructions.strip()

    def _build_prompt(self, state: SummaryState, task: TodoItem, context: str) -> str:
        guidance = build_note_guidance(task) if self._config.enable_notes else ""
        return (
            f"研究主题：{state.research_topic}\n"
            f"任务：{task.title}\n意图：{task.intent}\n查询：{task.query}\n"
            f"{guidance}\n检索上下文：\n{context}\n请输出该任务的简明总结。"
        )

    def summarize_task(self, state: SummaryState, task: TodoItem, context: str) -> str:
        prompt = self._build_prompt(state, task, context)
        response = invoke_llm(self._config, self._system, prompt)
        text = response.strip()
        if self._config.strip_thinking_tokens:
            text = strip_thinking_tokens(text)
        return strip_tool_calls(text).strip() or "暂无可用信息"

    def stream_task_summary(
        self, state: SummaryState, task: TodoItem, context: str
    ) -> Tuple[Iterator[str], Callable[[], str]]:
        prompt = self._build_prompt(state, task, context)
        remove_thinking = self._config.strip_thinking_tokens
        raw_buffer = ""
        visible_output = ""
        emit_index = 0

        def flush_visible() -> Iterator[str]:
            nonlocal emit_index, raw_buffer
            while True:
                start = raw_buffer.find("<think>", emit_index)
                if start == -1:
                    if emit_index < len(raw_buffer):
                        segment = raw_buffer[emit_index:]
                        emit_index = len(raw_buffer)
                        if segment:
                            yield segment
                    break
                if start > emit_index:
                    yield raw_buffer[emit_index:start]
                    emit_index = start
                end = raw_buffer.find("</think>", start)
                if end == -1:
                    break
                emit_index = end + len("</think>")

        def generator() -> Iterator[str]:
            nonlocal raw_buffer, visible_output, emit_index
            for chunk in stream_llm(self._config, self._system, prompt):
                raw_buffer += chunk
                if remove_thinking:
                    for segment in flush_visible():
                        visible_output += segment
                        if segment:
                            yield segment
                else:
                    visible_output += chunk
                    if chunk:
                        yield chunk

        def getter() -> str:
            text = visible_output.strip()
            if self._config.strip_thinking_tokens:
                text = strip_thinking_tokens(raw_buffer)
            return strip_tool_calls(text).strip() or "暂无可用信息"

        return generator(), getter
