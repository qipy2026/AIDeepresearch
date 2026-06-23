"""Dispatcher — 通过 lark-cli 推送橙色/红色预警。"""
from __future__ import annotations

import os
import subprocess
from typing import Any, Dict, List

from loguru import logger

_LARK_CLI = os.getenv("LARK_CLI_PATH", "")
if not _LARK_CLI:
    import shutil
    _LARK_CLI = shutil.which("lark-cli") or "lark-cli"


def _send_markdown(chat_id: str, markdown: str, as_identity: str = "bot") -> bool:
    """通过 lark-cli 发送 markdown 消息。"""
    try:
        result = subprocess.run(
            [_LARK_CLI, "im", "+messages-send",
             "--as", as_identity,
             "--chat-id", chat_id,
             "--markdown", markdown,
             "--format", "json"],
            capture_output=True, text=True, encoding="utf-8", timeout=15,
        )
        if result.returncode == 0:
            logger.info(f"飞书推送成功 → {chat_id}")
            return True
        logger.warning(f"飞书推送失败: {result.stderr[:200]}")
        return False
    except subprocess.TimeoutExpired:
        logger.warning("飞书推送超时")
        return False
    except Exception as e:
        logger.warning(f"飞书推送异常: {e}")
        return False


def push_alert(
    enterprise: str,
    severity: str,
    title: str,
    detail: str,
    source: str = "",
    suggested_action: str = "",
) -> bool:
    """推送预警到飞书群。

    Returns: True if push succeeded.
    """
    chat_id = os.getenv("WARNING_FEISHU_CHAT_ID", "")
    if not chat_id:
        logger.warning(
            f"🔴 预警未推送 (未配置 WARNING_FEISHU_CHAT_ID): {enterprise} | {severity} | {title}"
        )
        return False

    sev_emoji = {"red": "🔴", "orange": "🟠"}.get(severity, "🟡")

    md = f"{sev_emoji} **{severity}预警**: {enterprise}\n\n"
    md += f"**{title}**\n"
    if detail:
        md += f"{detail[:400]}\n"
    if source:
        md += f"\n📡 数据源: {source}"
    if suggested_action:
        md += f"\n💡 {suggested_action}"

    # 红色用加急（如果可用），橙色正常发送
    if severity == "red":
        md += "\n\n---\n⚠️ 请立即处理"

    return _send_markdown(chat_id, md)


def push_batch(alerts: List[Dict[str, Any]]) -> int:
    """批量推送预警，返回成功数。"""
    ok = 0
    for a in alerts:
        if push_alert(**a):
            ok += 1
    return ok
