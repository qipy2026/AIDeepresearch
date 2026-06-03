"""LangChain ChatOpenAI（替代 HelloAgentsLLM / ToolAwareSimpleAgent）。"""

from __future__ import annotations

import os
import time
from collections.abc import Iterator
from typing import Optional

from langchain_core.messages import AIMessage, HumanMessage, SystemMessage
from langchain_openai import ChatOpenAI

from config import Configuration


def _normalize_openai_base_url(url: str) -> str:
    """OpenAI 兼容客户端需要 base_url 以 /v1 结尾。"""
    normalized = url.strip().rstrip("/")
    if not normalized.endswith("/v1"):
        normalized = f"{normalized}/v1"
    return normalized


def build_chat_model(config: Configuration) -> ChatOpenAI:
    model_id = config.llm_model_id or config.local_llm or "gpt-4o-mini"
    provider = (config.llm_provider or "").strip().lower()
    api_key = config.llm_api_key or "ollama"
    base_url: Optional[str] = None

    if provider == "ollama":
        base_url = config.sanitized_ollama_url()
        if not config.llm_api_key:
            api_key = "ollama"
    elif provider == "lmstudio":
        base_url = config.lmstudio_base_url
    else:
        if config.llm_base_url:
            base_url = _normalize_openai_base_url(config.llm_base_url)

    return ChatOpenAI(
        model=model_id,
        api_key=api_key,
        base_url=base_url,
        temperature=0.0,
        max_tokens=config.llm_max_tokens,
        timeout=config.llm_timeout,
    )


def invoke_llm(
    config: Configuration,
    system_prompt: str,
    user_prompt: str,
    *,
    max_retries: Optional[int] = None,
) -> str:
    llm = build_chat_model(config)
    messages = [
        SystemMessage(content=system_prompt),
        HumanMessage(content=user_prompt),
    ]
    retries = max_retries if max_retries is not None else config.llm_max_retries
    last_err: Optional[Exception] = None
    for attempt in range(max(1, retries)):
        try:
            resp = llm.invoke(messages)
            return (resp.content or "").strip()
        except Exception as e:
            last_err = e
            msg = str(e).lower()
            if any(
                x in msg
                for x in ("500", "502", "503", "429", "timeout", "timed out", "connection")
            ):
                time.sleep(1.0 * (2**attempt))
                continue
            raise
    if last_err:
        raise last_err
    return ""


def stream_llm(
    config: Configuration,
    system_prompt: str,
    user_prompt: str,
) -> Iterator[str]:
    llm = build_chat_model(config)
    messages = [
        SystemMessage(content=system_prompt),
        HumanMessage(content=user_prompt),
    ]
    for chunk in llm.stream(messages):
        if chunk.content:
            yield str(chunk.content)
