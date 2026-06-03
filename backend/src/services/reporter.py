"""最终报告（LangChain LLM）。"""

from __future__ import annotations

from config import Configuration
from core.llm import invoke_llm
from models import SummaryState
from prompts import report_writer_instructions
from services.notes_store import NotesStore
from services.text_processing import strip_tool_calls
from utils import strip_thinking_tokens


class ReportingService:
    def __init__(self, config: Configuration, notes: NotesStore | None = None) -> None:
        self._config = config
        self._system = report_writer_instructions.strip()
        self._notes = notes

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

        prompt = (
            f"研究主题：{state.research_topic}\n\n"
            f"任务与总结：\n{''.join(tasks_block)}\n"
        )
        if notes_block:
            prompt += f"\n任务笔记摘录：\n{''.join(notes_block)}\n"
        prompt += "\n请整合以上信息，撰写结构完整的中文 Markdown 研究报告。"

        response = invoke_llm(self._config, self._system, prompt)
        report_text = response.strip()
        if self._config.strip_thinking_tokens:
            report_text = strip_thinking_tokens(report_text)
        return strip_tool_calls(report_text).strip() or "报告生成失败，请检查输入。"
