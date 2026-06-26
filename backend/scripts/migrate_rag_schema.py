"""执行 DDL 建表迁移"""
import os
import sys
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from mysql_client import MySQLClient
from pathlib import Path


def main():
    db = MySQLClient()
    if not db.health():
        print("ERROR: MySQL 不可达")
        sys.exit(1)

    sql_path = Path(__file__).parent.parent / "migrations" / "001_rag_tables.sql"
    sql = sql_path.read_text(encoding="utf-8")

    statements = [s.strip() for s in sql.split(";") if s.strip()]
    for stmt in statements:
        try:
            db.execute(stmt)
            print(f"OK: {stmt[:60]}...")
        except Exception as e:
            print(f"SKIP (may already exist): {e}")

    rows = db.query("SHOW TABLES LIKE 'rag_%'")
    print(f"Tables created: {[list(r.values())[0] for r in rows]}")
    print("Migration complete.")


if __name__ == "__main__":
    main()
