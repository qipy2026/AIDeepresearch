"""将 ChromaDB 中现有数据的企业/文档元数据迁移到 MySQL

不重建向量，只迁移索引关系。
"""
import os
import sys
from collections import defaultdict

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from services.chroma_store import ChromaStore
from mysql_client import MySQLClient
from services.rag_repo import RagRepo


def main():
    db = MySQLClient()
    if not db.health():
        print("ERROR: MySQL 不可达，请检查环境变量 MYSQL_HOST/MYSQL_PORT/MYSQL_USER/MYSQL_PASSWORD/MYSQL_DATABASE")
        sys.exit(1)

    repo = RagRepo(db)
    repo.init_tables()

    # 从 ChromaDB 读取所有 metadata
    print("Reading ChromaDB metadata...")
    chroma = ChromaStore()
    all_meta = chroma.get_all_metadata()
    print(f"Total chunks in ChromaDB: {len(all_meta)}")

    if not all_meta:
        print("No data in ChromaDB. Nothing to migrate.")
        return

    # 按 enterprise 分组统计
    enterprise_chunks: dict[str, int] = defaultdict(int)
    for m in all_meta:
        ent = m.get("enterprise", "")
        if ent:
            enterprise_chunks[ent] += 1

    print(f"Unique enterprises: {len(enterprise_chunks)}")

    # 写入 MySQL
    for ent in sorted(enterprise_chunks):
        total_chunks = enterprise_chunks[ent]

        # 企业记录
        repo.upsert_enterprise(ent)

        # 创建聚合文档记录（历史数据）
        doc_id = repo.insert_document(ent, "(历史数据)", 0)
        repo.mark_document_active(doc_id, total_chunks)
        repo.increment_enterprise(ent, 1, total_chunks)
        print(f"  Migrated: {ent} ({total_chunks} chunks)")

    # 验证
    enterprises = repo.list_enterprises()
    print(f"\nMigration complete. {len(enterprises)} enterprises in MySQL.")
    for e in enterprises:
        print(f"  {e['name']}: {e['doc_count']} docs, {e['chunk_count']} chunks")


if __name__ == "__main__":
    main()
