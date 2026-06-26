"""MySQL client — short connection mode, open/close per operation"""
from __future__ import annotations

import os
import pymysql
from pymysql.cursors import DictCursor


class MySQLClient:
    """Lightweight MySQL client, creates a new connection per query/execute"""

    def __init__(self):
        self.host = os.getenv("MYSQL_HOST", "localhost")
        self.port = int(os.getenv("MYSQL_PORT", "3306"))
        self.user = os.getenv("MYSQL_USER", "root")
        self.password = os.getenv("MYSQL_PASSWORD", "")
        self.database = os.getenv("MYSQL_DATABASE", "rag_db")
        self.charset = "utf8mb4"

    def _connect(self):
        return pymysql.connect(
            host=self.host,
            port=self.port,
            user=self.user,
            password=self.password,
            database=self.database,
            charset=self.charset,
            cursorclass=DictCursor,
            autocommit=True,
        )

    def execute(self, sql: str, params=None) -> int:
        """Execute a write operation, returns lastrowid"""
        conn = self._connect()
        try:
            with conn.cursor() as cursor:
                cursor.execute(sql, params)
                return cursor.lastrowid
        finally:
            conn.close()

    def query(self, sql: str, params=None) -> list[dict]:
        """Execute a read operation, returns list of dicts"""
        conn = self._connect()
        try:
            with conn.cursor() as cursor:
                cursor.execute(sql, params)
                return cursor.fetchall()
        finally:
            conn.close()

    def health(self) -> bool:
        """Health check"""
        try:
            conn = self._connect()
            with conn.cursor() as cursor:
                cursor.execute("SELECT 1")
            conn.close()
            return True
        except Exception:
            return False
