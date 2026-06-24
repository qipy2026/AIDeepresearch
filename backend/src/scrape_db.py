"""原始素材数据库 — 与预警日志分离，供人工审计。"""
from __future__ import annotations

import sqlite3
from datetime import datetime
from pathlib import Path

DB_PATH = Path(__file__).resolve().parent.parent / "postloan.db"


def get_db() -> sqlite3.Connection:
    conn = sqlite3.connect(str(DB_PATH))
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    return conn


def init():
    conn = get_db()
    conn.execute("""
        CREATE TABLE IF NOT EXISTS scrape_source (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            enterprise TEXT NOT NULL,
            source TEXT NOT NULL,
            source_url TEXT NOT NULL,
            title TEXT NOT NULL,
            content TEXT NOT NULL,
            llm_direction TEXT DEFAULT '',
            llm_summary TEXT DEFAULT '',
            credible INTEGER DEFAULT NULL,
            created_at TEXT NOT NULL DEFAULT (datetime('now','localtime'))
        )
    """)
    conn.execute("CREATE INDEX IF NOT EXISTS idx_scrape_enterprise ON scrape_source(enterprise)")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_scrape_created ON scrape_source(created_at)")
    conn.commit()
    conn.close()


def insert(enterprise: str, source: str, source_url: str, title: str,
           content: str, llm_direction: str = "", llm_summary: str = "") -> int:
    conn = get_db()
    cur = conn.execute(
        "INSERT INTO scrape_source (enterprise, source, source_url, title, content, llm_direction, llm_summary) VALUES (?,?,?,?,?,?,?)",
        (enterprise, source, source_url, title, content, llm_direction, llm_summary),
    )
    conn.commit()
    row_id = cur.lastrowid
    conn.close()
    return row_id


def list_sources(enterprise: str = "", limit: int = 100) -> list[dict]:
    conn = get_db()
    if enterprise:
        rows = conn.execute(
            "SELECT * FROM scrape_source WHERE enterprise=? ORDER BY created_at DESC LIMIT ?",
            (enterprise, limit),
        ).fetchall()
    else:
        rows = conn.execute(
            "SELECT * FROM scrape_source ORDER BY created_at DESC LIMIT ?",
            (limit,),
        ).fetchall()
    conn.close()
    return [dict(r) for r in rows]


def mark_credible(source_id: int, credible: bool):
    conn = get_db()
    conn.execute("UPDATE scrape_source SET credible=? WHERE id=?", (1 if credible else 0, source_id))
    conn.commit()
    conn.close()


def stats() -> dict:
    conn = get_db()
    total = conn.execute("SELECT COUNT(*) FROM scrape_source").fetchone()[0]
    credible_count = conn.execute("SELECT COUNT(*) FROM scrape_source WHERE credible=1").fetchone()[0]
    not_credible = conn.execute("SELECT COUNT(*) FROM scrape_source WHERE credible=0").fetchone()[0]
    conn.close()
    return {"total": total, "credible": credible_count, "not_credible": not_credible}
