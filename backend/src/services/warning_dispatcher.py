"""Dispatcher — 飞书推送橙色/红色预警。"""
from __future__ import annotations

import json
import os
from typing import Any, Dict, List

import requests
from loguru import logger


def push_alert(
    enterprise: str,
    severity: str,
    title: str,
    detail: str,
    source: str = "",
    suggested_action: str = "",
) -> bool:
    """推送预警到飞书。

    Returns: True if push succeeded, False otherwise.
    """
    webhook = os.getenv("FEISHU_BOT_WEBHOOK_URL", "")
    token = os.getenv("FEISHU_BOT_TOKEN", "")

    sev_emoji = {"red": "🔴", "orange": "🟠"}.get(severity, "🟡")
    sev_text = {"red": "红色预警", "orange": "橙色预警"}.get(severity, severity)

    # 飞书卡片消息
    card = {
        "msg_type": "interactive",
        "card": {
            "header": {
                "title": {"tag": "plain_text", "content": f"{sev_emoji} {sev_text}: {enterprise}"},
                "template": "red" if severity == "red" else "orange",
            },
            "elements": [
                {"tag": "div", "text": {"tag": "lark_md", "content": f"**{title}**"}},
                {"tag": "div", "text": {"tag": "lark_md", "content": detail[:500]}},
            ],
        },
    }
    if source:
        card["card"]["elements"].append(
            {"tag": "div", "text": {"tag": "lark_md", "content": f"📡 数据源: {source}"}}
        )
    if suggested_action:
        card["card"]["elements"].append(
            {"tag": "div", "text": {"tag": "lark_md", "content": f"💡 建议: {suggested_action}"}}
        )

    # 尝试 webhook 推送
    if webhook:
        try:
            resp = requests.post(webhook, json=card, timeout=10)
            if resp.status_code == 200:
                logger.info(f"飞书推送成功: {enterprise} {severity}")
                return True
            logger.warning(f"飞书推送失败 HTTP {resp.status_code}: {resp.text[:200]}")
        except Exception as e:
            logger.warning(f"飞书推送异常: {e}")

    # 尝试 Bot API 推送
    if token:
        try:
            resp = requests.post(
                "https://open.feishu.cn/open-apis/im/v1/messages?receive_id_type=chat_id",
                json={
                    "receive_id": os.getenv("FEISHU_CHAT_ID", ""),
                    "msg_type": "interactive",
                    "content": json.dumps(card["card"]),
                },
                headers={"Authorization": f"Bearer {token}", "Content-Type": "application/json"},
                timeout=10,
            )
            if resp.status_code == 200:
                logger.info(f"飞书Bot推送成功: {enterprise}")
                return True
        except Exception as e:
            logger.warning(f"飞书Bot推送异常: {e}")

    # 无可用推送渠道 → 日志告警
    logger.warning(
        "🔴 预警无法推送 (未配置 FEISHU_BOT_WEBHOOK_URL 或 FEISHU_BOT_TOKEN): "
        f"{enterprise} | {severity} | {title}"
    )
    return False


def push_batch(alerts: List[Dict[str, Any]]) -> int:
    """批量推送预警，返回成功数。"""
    ok = 0
    for a in alerts:
        if push_alert(**a):
            ok += 1
    return ok
