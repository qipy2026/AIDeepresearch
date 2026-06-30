"""RAG MySQL 数据访问层"""
from __future__ import annotations


class RagRepo:
    """RAG 企业-文档索引的 MySQL CRUD"""

    def __init__(self, mysql_client):
        self.db = mysql_client

    def init_tables(self):
        """执行 DDL（幂等，CREATE TABLE IF NOT EXISTS）"""
        sql = """
        CREATE TABLE IF NOT EXISTS rag_enterprises (
            id          BIGINT AUTO_INCREMENT PRIMARY KEY,
            name        VARCHAR(255) NOT NULL,
            doc_count   INT NOT NULL DEFAULT 0,
            chunk_count INT NOT NULL DEFAULT 0,
            created_at  DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
            updated_at  DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
            UNIQUE KEY uk_name (name),
            INDEX idx_name (name)
        ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

        CREATE TABLE IF NOT EXISTS rag_documents (
            id           BIGINT AUTO_INCREMENT PRIMARY KEY,
            enterprise   VARCHAR(255) NOT NULL,
            filename     VARCHAR(512) NOT NULL,
            file_size    BIGINT NOT NULL DEFAULT 0,
            chunk_count  INT NOT NULL DEFAULT 0,
            minio_path   VARCHAR(1024) DEFAULT NULL,
            status       ENUM('uploading','active','failed','deleted') NOT NULL DEFAULT 'uploading',
            error_msg    TEXT DEFAULT NULL,
            created_at   DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
            updated_at   DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
            INDEX idx_enterprise (enterprise),
            INDEX idx_status (status),
            CONSTRAINT fk_rag_docs_enterprise FOREIGN KEY (enterprise)
                REFERENCES rag_enterprises(name) ON DELETE CASCADE
        ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;
        """
        for stmt in [s.strip() for s in sql.split(";") if s.strip()]:
            try:
                self.db.execute(stmt)
            except Exception:
                pass  # 已存在的表/约束忽略

    # ── enterprise ──

    def upsert_enterprise(self, name: str) -> None:
        self.db.execute(
            "INSERT INTO rag_enterprises (name) VALUES (%s) "
            "ON DUPLICATE KEY UPDATE name=name",
            (name,),
        )

    def list_enterprises(self) -> list[dict]:
        return self.db.query(
            "SELECT name, doc_count, chunk_count, updated_at AS last_upload "
            "FROM rag_enterprises "
            "ORDER BY updated_at DESC"
        )

    def increment_enterprise(self, name: str, doc_delta: int, chunk_delta: int) -> None:
        self.db.execute(
            "UPDATE rag_enterprises SET doc_count = doc_count + %s, "
            "chunk_count = chunk_count + %s WHERE name = %s",
            (doc_delta, chunk_delta, name),
        )

    def delete_enterprise(self, name: str) -> None:
        self.db.execute("DELETE FROM rag_enterprises WHERE name = %s", (name,))

    # ── document ──

    def insert_document(self, enterprise: str, filename: str, file_size: int) -> int:
        return self.db.execute(
            "INSERT INTO rag_documents (enterprise, filename, file_size, status) "
            "VALUES (%s, %s, %s, 'uploading')",
            (enterprise, filename, file_size),
        )

    def mark_document_active(
        self, doc_id: int, chunk_count: int, minio_path: str | None = None
    ) -> None:
        self.db.execute(
            "UPDATE rag_documents SET status='active', chunk_count=%s, "
            "minio_path=%s WHERE id=%s",
            (chunk_count, minio_path, doc_id),
        )

    def mark_document_failed(self, doc_id: int, error_msg: str) -> None:
        self.db.execute(
            "UPDATE rag_documents SET status='failed', error_msg=%s WHERE id=%s",
            (error_msg, doc_id),
        )

    def get_documents(self, enterprise: str) -> list[dict]:
        return self.db.query(
            "SELECT id, filename, file_size, chunk_count, minio_path, "
            "status, error_msg, created_at "
            "FROM rag_documents WHERE enterprise=%s AND status!='deleted' "
            "ORDER BY created_at DESC",
            (enterprise,),
        )

    def get_doc_ids_for_enterprise(self, name: str) -> list[int]:
        rows = self.db.query(
            "SELECT id FROM rag_documents WHERE enterprise=%s", (name,)
        )
        return [r["id"] for r in rows]

    def get_document_by_id(self, doc_id: int) -> dict | None:
        rows = self.db.query(
            "SELECT * FROM rag_documents WHERE id=%s", (doc_id,)
        )
        return rows[0] if rows else None
