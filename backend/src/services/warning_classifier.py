"""Classifier Agent — L1 关键词预筛 + L2 LLM 精细分级。"""
from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any, Dict, List

import yaml
from loguru import logger


class ClassifierService:
    """两级分类器：L1关键词（毫秒级）+ L2 LLM（按需调用）。"""

    def __init__(self, keywords_path: str = ""):
        path = keywords_path or str(
            Path(__file__).resolve().parent.parent.parent
            / "config" / "keywords.yaml"
        )
        with open(path, "r", encoding="utf-8") as f:
            data = yaml.safe_load(f) or {}
        self._fatal = [kw.lower() for kw in data.get("fatal", [])]
        self._severe = [kw.lower() for kw in data.get("severe", [])]
        self._watch = [kw.lower() for kw in data.get("watch", [])]

    def classify(
        self, text: str, enterprise: str = "", do_l2: bool = True
    ) -> Dict[str, Any]:
        """L1 关键词匹配 + 可选的 L2 LLM 分级。

        Returns:
            {severity, category, title, detail, suggested_action}
        """
        default: Dict[str, Any] = {
            "severity": "none", "category": "", "title": text[:100],
            "detail": text[:500], "suggested_action": "",
        }
        if not text.strip():
            return default

        t = text.lower()

        # Fatal → 直接红色，跳过后续检查
        for kw in self._fatal:
            if kw in t:
                return {
                    **default,
                    "severity": "red",
                    "category": "安全/法律",
                    "title": f"致命信号: {kw}",
                    "detail": text[:500],
                    "suggested_action": "立即核实，启动风险应对流程",
                }

        has_severe = any(kw in t for kw in self._severe)
        has_watch = any(kw in t for kw in self._watch)
        if not has_severe and not has_watch:
            return default

        l1 = "orange" if has_severe else "yellow"
        if do_l2:
            return self._l2_classify(text, enterprise, l1)

        return {**default, "severity": l1, "title": "关键词匹配", "detail": text[:500]}

    def _l2_classify(
        self, text: str, enterprise: str, l1_severity: str
    ) -> Dict[str, Any]:
        try:
            from core.llm import invoke_llm
            from config import Configuration

            prompt = (
                "你是贷后风险分析师。对企业信号进行分级。\n\n"
                f"企业: {enterprise}\n"
                f"信号: {text[:1000]}\n"
                f"L1预分级: {l1_severity}\n\n"
                "以JSON返回: {\"severity\":\"red|orange|yellow|none\","
                "\"category\":\"舆情|金融|经营|法律|安全\","
                "\"title\":\"一句话\",\"detail\":\"说明\","
                "\"suggested_action\":\"建议\"}\n"
                "red=贷款损失 imminent, orange=偿付恶化, yellow=关注"
            )
            config = Configuration.from_env()
            resp = invoke_llm(config, prompt, "")
            m = re.search(r"\{[^{}]*\}", resp)
            if m:
                result = json.loads(m.group(0))
                result.setdefault("category", "")
                result.setdefault("title", text[:100])
                result.setdefault("detail", text[:500])
                result.setdefault("suggested_action", "")
                return result
            return {"severity": l1_severity, "category": "",
                    "title": text[:100], "detail": text[:500],
                    "suggested_action": ""}
        except Exception as e:
            logger.warning(f"L2 classify failed: {e}, fallback to L1")
            return {"severity": l1_severity, "category": "",
                    "title": text[:100], "detail": text[:500],
                    "suggested_action": ""}
