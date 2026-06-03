"""搜索入口（实现见 web_search.py）。"""

from __future__ import annotations

from typing import Any, Optional, Tuple

from config import Configuration
from utils import deduplicate_and_format_sources, format_sources
from services.web_search import dispatch_search

MAX_TOKENS_PER_SOURCE = 2000


def prepare_research_context(
    search_result: dict[str, Any] | None,
    answer_text: Optional[str],
    config: Configuration,
) -> tuple[str, str]:
    sources_summary = format_sources(search_result)
    context = deduplicate_and_format_sources(
        search_result or {"results": []},
        max_tokens_per_source=MAX_TOKENS_PER_SOURCE,
        fetch_full_page=config.fetch_full_page,
    )
    if answer_text:
        context = f"AI直接答案：\n{answer_text}\n\n{context}"
    return sources_summary, context
