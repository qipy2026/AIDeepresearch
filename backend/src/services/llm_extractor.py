"""LLM 关联提取 —— 从非结构化文本中识别实体、关系、风险方向。"""
from __future__ import annotations

import json
import logging
import os

from dotenv import load_dotenv
from openai import OpenAI

logger = logging.getLogger(__name__)

_client: OpenAI | None = None


def _get_client() -> OpenAI:
    global _client
    if _client is None:
        load_dotenv()
        _client = OpenAI(
            api_key=os.getenv("LLM_API_KEY", ""),
            base_url=os.getenv("LLM_BASE_URL", "https://api.deepseek.com/v1"),
        )
    return _client


SYSTEM_PROMPT = """你是一个贷后风险分析助手。你会收到一份上市公司的公告文本，以及一个监管企业列表。
你的任务：
1. 从公告中提取对监管企业有影响的关键信息
2. 判断影响方向：positive（利好，如中标大单/业绩增长）、negative（利空，如亏损/诉讼/违约）、neutral（中性，如例行公告）
3. 返回 JSON

只返回 JSON，不要任何解释。
JSON 格式：
{
  "relevant_enterprises": [
    {
      "enterprise_name": "企业名",
      "direction": "positive|negative|neutral",
      "confidence": 0.0-1.0,
      "summary": "一句话总结关键影响",
      "key_facts": ["事实1", "事实2"]
    }
  ],
  "irrelevant": true/false
}
如果没有关联任何企业，返回 {"irrelevant": true, "relevant_enterprises": []}
"""


def extract_and_classify(text: str, enterprises: list[dict]) -> dict:
    """用 LLM 从公告文本中提取关联企业并判断风险方向。

    Args:
        text: 公告文本（纯文本）
        enterprises: 企业列表，每个含 name, role, debtor 等字段

    Returns:
        {relevant_enterprises: [...], irrelevant: bool}
    """
    if not text or len(text.strip()) < 20:
        return {"irrelevant": True, "relevant_enterprises": []}

    # 构建企业上下文
    ent_list = []
    for e in enterprises:
        info = f"- {e['name']}（{e.get('role','')}）"
        if e.get("debtor"):
            info += f" → 债务人: {e['debtor']}"
        if e.get("parent"):
            info += f" → 母公司: {e['parent']}"
        ent_list.append(info)
    ent_context = "\n".join(ent_list)

    user_prompt = f"""公告文本：
---
{text[:3000]}
---

监管企业列表：
{ent_context}

请分析此公告对这些企业的影响。"""

    try:
        client = _get_client()
        resp = client.chat.completions.create(
            model=os.getenv("LLM_MODEL_ID", "deepseek-v4-flash"),
            messages=[
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": user_prompt},
            ],
            temperature=0.1,
            max_tokens=1000,
            timeout=int(os.getenv("LLM_TIMEOUT", "60")),
        )
        content = resp.choices[0].message.content.strip()
        # 清理可能的 markdown 代码块
        if content.startswith("```"):
            content = content.split("\n", 1)[-1]
            if content.endswith("```"):
                content = content[:-3]
            content = content.strip()
        return json.loads(content)
    except json.JSONDecodeError as e:
        logger.warning("LLM returned invalid JSON: %s", str(e)[:200])
        return {"irrelevant": True, "relevant_enterprises": []}
    except Exception as e:
        logger.warning("LLM extraction failed: %s", e)
        return {"irrelevant": True, "relevant_enterprises": []}


def classify_to_severity(direction: str, confidence: float) -> str:
    """将 LLM 输出映射为预警级别。"""
    if direction == "negative":
        if confidence >= 0.8:
            return "orange"
        return "yellow"
    elif direction == "positive":
        return "normal"
    return "normal"
