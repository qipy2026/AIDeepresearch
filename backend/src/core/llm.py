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


FALLBACK_MODELS = [
    "deepseek-v4-pro",
]


def _try_model(
    config: Configuration,
    model_id: str,
    messages: list,
    retries: int,
) -> Optional[str]:
    """尝试用指定模型调用 LLM，返回 None 表示所有重试均失败。"""
    llm = ChatOpenAI(
        model=model_id,
        api_key=config.llm_api_key or "ollama",
        base_url=(
            _normalize_openai_base_url(config.llm_base_url)
            if config.llm_base_url else None
        ),
        temperature=0.0,
        max_tokens=config.llm_max_tokens,
        timeout=config.llm_timeout,
    )
    for attempt in range(retries):
        try:
            resp = llm.invoke(messages)
            return (resp.content or "").strip()
        except Exception as e:
            msg = str(e).lower()
            if any(
                x in msg
                for x in ("500", "502", "503", "429", "timeout", "timed out", "connection")
            ):
                time.sleep(1.0 * (2**attempt))
                continue
            return None  # 非可重试错误，不降级
    return None


def invoke_llm(
    config: Configuration,
    system_prompt: str,
    user_prompt: str,
    *,
    max_retries: Optional[int] = None,
) -> str:
    messages = [
        SystemMessage(content=system_prompt),
        HumanMessage(content=user_prompt),
    ]
    retries = max(1, max_retries if max_retries is not None else config.llm_max_retries)

    # 主模型
    primary = config.llm_model_id or config.local_llm or "gpt-4o-mini"
    result = _try_model(config, primary, messages, retries)
    if result is not None:
        return result

    # 降级链
    for fallback in FALLBACK_MODELS:
        if fallback == primary:
            continue
        result = _try_model(config, fallback, messages, retries)
        if result is not None:
            return result

    raise RuntimeError(
        f"LLM 调用失败: 主模型 {primary} 及全部备选模型 {FALLBACK_MODELS} 均不可用"
    )


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
