"""预警日志数据库（SQLite WAL 模式）。"""
from __future__ import annotations

import hashlib
import sqlite3
from typing import Any, Dict, List, Optional


class WarningDB:
    """预警日志持久层。"""

    def __init__(self, db_path: str = "postloan.db"):
        self._path = db_path
        self._conn: Optional[sqlite3.Connection] = None

    def _get_conn(self) -> sqlite3.Connection:
        if self._conn is None:
            self._conn = sqlite3.connect(
                self._path, check_same_thread=False
            )
            self._conn.row_factory = sqlite3.Row
            self._conn.execute("PRAGMA journal_mode=WAL;")
            self._conn.execute("PRAGMA busy_timeout=5000;")
        return self._conn

    def init(self):
        conn = self._get_conn()
        conn.executescript("""
            CREATE TABLE IF NOT EXISTS warning_log (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                enterprise TEXT NOT NULL,
                source TEXT NOT NULL,
                severity TEXT NOT NULL,
                category TEXT DEFAULT '',
                title TEXT NOT NULL,
                detail TEXT DEFAULT '',
                suggested_action TEXT DEFAULT '',
                content_hash TEXT UNIQUE,
                status TEXT DEFAULT 'new',
                acked_by TEXT DEFAULT '',
                acked_at TEXT DEFAULT '',
                created_at TEXT DEFAULT (datetime('now','localtime')),
                raw_data TEXT DEFAULT '',
                source_url TEXT DEFAULT ''
            );
            CREATE INDEX IF NOT EXISTS idx_w_enterprise ON warning_log(enterprise);
            CREATE INDEX IF NOT EXISTS idx_w_severity ON warning_log(severity);
            CREATE INDEX IF NOT EXISTS idx_w_status ON warning_log(status);
            CREATE INDEX IF NOT EXISTS idx_w_created ON warning_log(created_at);
        """)
        # migration: add source_url column for existing databases
        try:
            conn.execute("ALTER TABLE warning_log ADD COLUMN source_url TEXT DEFAULT ''")
        except sqlite3.OperationalError:
            pass
        conn.commit()

    @staticmethod
    def _hash(enterprise: str, source: str, title: str) -> str:
        raw = f"{enterprise}|{source}|{title}".encode("utf-8")
        return hashlib.sha256(raw).hexdigest()[:32]

    def insert(
        self, enterprise: str, source: str, severity: str,
        category: str, title: str, detail: str,
        suggested_action: str, raw_data: str = "",
        source_url: str = "",
    ) -> int:
        conn = self._get_conn()
        ch = self._hash(enterprise, source, title)
        try:
            conn.execute(
                """INSERT INTO warning_log
                   (enterprise, source, severity, category, title,
                    detail, suggested_action, content_hash, raw_data, source_url)
                   VALUES (?,?,?,?,?,?,?,?,?,?)""",
                (enterprise, source, severity, category, title,
                 detail, suggested_action, ch, raw_data, source_url),
            )
            conn.commit()
            row = conn.execute("SELECT last_insert_rowid()").fetchone()
            return row[0] if row else 0
        except sqlite3.IntegrityError:
            conn.execute(
                """UPDATE warning_log
                   SET created_at = datetime('now','localtime')
                   WHERE content_hash = ?""", (ch,),
            )
            conn.commit()
            row = conn.execute(
                "SELECT id FROM warning_log WHERE content_hash = ?",
                (ch,),
            ).fetchone()
            return row[0] if row else 0

    def get(self, warning_id: int) -> Optional[Dict[str, Any]]:
        row = self._get_conn().execute(
            "SELECT * FROM warning_log WHERE id = ?", (warning_id,)
        ).fetchone()
        return dict(row) if row else None

    def list_warnings(
        self, enterprise: str = "", severity: str = "",
        status: str = "", limit: int = 50, offset: int = 0,
    ) -> List[Dict[str, Any]]:
        conn = self._get_conn()
        parts = ["1=1"]
        params: list = []
        if enterprise:
            parts.append("enterprise = ?"); params.append(enterprise)
        if severity:
            parts.append("severity = ?"); params.append(severity)
        if status:
            parts.append("status = ?"); params.append(status)
        sql = (
            f"SELECT * FROM warning_log WHERE {' AND '.join(parts)} "
            f"ORDER BY created_at DESC LIMIT ? OFFSET ?"
        )
        params.extend([limit, offset])
        return [dict(r) for r in conn.execute(sql, params).fetchall()]

    def ack(self, warning_id: int, acked_by: str):
        self._get_conn().execute(
            """UPDATE warning_log
               SET status='acked', acked_by=?,
                   acked_at=datetime('now','localtime')
               WHERE id=?""", (acked_by, warning_id),
        )
        self._get_conn().commit()

    def mark_false(self, warning_id: int, acked_by: str):
        self._get_conn().execute(
            """UPDATE warning_log
               SET status='false_positive', acked_by=?,
                   acked_at=datetime('now','localtime')
               WHERE id=?""", (acked_by, warning_id),
        )
        self._get_conn().commit()

    def reset_status(self, warning_id: int):
        """撤销误报，回到 new 状态。"""
        self._get_conn().execute(
            """UPDATE warning_log
               SET status='new', acked_by='', acked_at=''
               WHERE id=?""", (warning_id,),
        )
        self._get_conn().commit()

    def set_severity(self, warning_id: int, severity: str):
        """人工覆盖预警级别。"""
        self._get_conn().execute(
            "UPDATE warning_log SET severity=? WHERE id=?",
            (severity, warning_id),
        )
        self._get_conn().commit()

    def stats(self) -> Dict[str, Any]:
        conn = self._get_conn()
        sev = conn.execute(
            "SELECT severity, COUNT(*) as cnt FROM warning_log GROUP BY severity"
        ).fetchall()
        st = conn.execute(
            "SELECT status, COUNT(*) as cnt FROM warning_log GROUP BY status"
        ).fetchall()
        return {
            "by_severity": {r["severity"]: r["cnt"] for r in sev},
            "by_status": {r["status"]: r["cnt"] for r in st},
        }
