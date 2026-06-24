"""企业信息自动补全 — Tier 1: LLM 从企业名推断行业和搜索关键词。

调用约定:
- enrich(name, role) 返回 EnrichmentResult (dict)，不写 YAML
- 调用方 (main.py add-enterprise API) 决定是否持久化
"""

from __future__ import annotations

import json
import logging
from typing import Optional

logger = logging.getLogger(__name__)

ENRICH_SYSTEM_PROMPT = """你是一个企业信息补全助手。根据企业名称推断行业和搜索关键词。

规则:
- industry: 从企业名称中提取行业信号词。如含"物业"→"物业管理"，含"保安"→"安保服务"，含"管道/输油/输气"→"管道运输"，含"建筑/铁建"→"建筑施工"，含"能投/能源"→"综合能源服务"，含"房地产/城都汇"→"房地产开发"
- keywords: 2-3个搜索关键词，含企业短名（去"有限/股份/分公司/责任"后缀）
- confidence: 对推断结果的置信度 0.0-1.0。企业名含明确行业信号词(power≥0.8)，模糊但可推断(0.5-0.7)，无信号词(<0.5)"""


class EnrichmentResult(dict):
    """Tier 1 enrichment 返回结构。"""
    industry: Optional[str] = None
    keywords: list[str] = []
    confidence: float = 0.0
    skipped: bool = False
    reason: str = ""


def _build_enrich_prompt(name: str, role: str) -> str:
    role_desc = "借款方(乙方)" if role == "乙方" else "核心监管方(甲方)"
    return f"""企业名称: {name}
角色: {role} ({role_desc})

请返回JSON，不要多余文本:
{{"industry": "行业分类", "keywords": ["关键词1", "关键词2"], "confidence": 0.0-1.0}}"""


def enrich(name: str, role: str = "乙方", *, config=None) -> EnrichmentResult:
    """Tier 1: LLM 推断行业+关键词（同步）。

    Args:
        name: 企业全称
        role: 乙方/甲方
        config: Configuration 实例（可选，不传则从 env 构建）

    Returns:
        EnrichmentResult with industry, keywords, confidence fields
    """
    if config is None:
        from config import Configuration
        config = Configuration.from_env()

    try:
        from core.llm import invoke_llm

        user_prompt = _build_enrich_prompt(name, role)
        raw = invoke_llm(config, ENRICH_SYSTEM_PROMPT, user_prompt, max_retries=1)

        # Extract JSON from response (strip markdown code fences if present)
        raw = raw.strip()
        if raw.startswith("```"):
            lines = raw.split("\n")
            raw = "\n".join(lines[1:-1] if lines[-1].strip() == "```" else lines[1:])

        result = json.loads(raw)
        confidence = float(result.get("confidence", 0.0))
        industry = str(result.get("industry", "")).strip()
        keywords = [str(k).strip() for k in result.get("keywords", []) if k]

        if confidence < 0.5:
            logger.info("enricher: low confidence %.2f for %s", confidence, name)
            return EnrichmentResult({
                "industry": None,
                "keywords": [],
                "confidence": confidence,
                "skipped": True,
                "reason": "low confidence",
            })

        logger.info("enricher: %s → industry=%s keywords=%s (conf=%.2f)",
                     name, industry, keywords, confidence)
        return EnrichmentResult({
            "industry": industry,
            "keywords": keywords,
            "confidence": confidence,
            "skipped": False,
            "reason": "",
        })

    except json.JSONDecodeError as e:
        logger.warning("enricher: JSON parse failed for %s: %s", name, e)
        return EnrichmentResult({
            "industry": None,
            "keywords": [],
            "confidence": 0.0,
            "skipped": True,
            "reason": f"JSON parse error: {e}",
        })
    except Exception as e:
        msg = str(e).lower()
        if any(x in msg for x in ("timeout", "connection", "500", "502", "503", "429")):
            logger.warning("enricher: LLM unavailable for %s: %s", name, e)
        else:
            logger.error("enricher: unexpected error for %s: %s", name, e)
        return EnrichmentResult({
            "industry": None,
            "keywords": [],
            "confidence": 0.0,
            "skipped": True,
            "reason": f"LLM error: {e}",
        })
