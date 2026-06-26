"""RAG 服务编排层 — 原子上传、列表查询、联动删除"""
from __future__ import annotations

import logging
from io import BytesIO

logger = logging.getLogger(__name__)


class RagService:
    """RAG 统一服务入口"""

    def __init__(self, repo, chroma_store, chunker, minio_storage=None):
        self.repo = repo
        self.chroma = chroma_store
        self.chunker = chunker
        self.minio = minio_storage

    # ── 上传（原子化）──

    def upload_file(
        self, enterprise: str, filename: str, content_bytes: bytes
    ) -> dict:
        """原子上传：先写 ChromaDB → 成功写 MySQL → 失败回滚"""
        enterprise = enterprise.strip()
        logger.info("rag.upload.start", extra={
            "enterprise": enterprise, "filename": filename, "file_size": len(content_bytes)
        })

        # 1. 幂等确保企业记录存在
        self.repo.upsert_enterprise(enterprise)

        # 2. 插入文档记录 (status='uploading')
        doc_id = self.repo.insert_document(enterprise, filename, len(content_bytes))

        # 3. 提取文本 → 分块
        text = self._extract_text(content_bytes, filename)
        if not text.strip():
            self.repo.mark_document_failed(doc_id, "文件内容为空")
            return {"status": "error", "enterprise": enterprise, "error": "文件内容为空"}

        chunks = self.chunker.chunk(text)
        logger.info("rag.upload.chunk", extra={
            "doc_id": doc_id, "chunks": len(chunks), "chunk_size": self.chunker.chunk_size
        })

        # 4. 写入 ChromaDB
        try:
            self.chroma.add_chunks(chunks, enterprise, doc_id)
        except Exception as e:
            self.repo.mark_document_failed(doc_id, f"ChromaDB写入失败: {e}")
            logger.error("rag.chromadb.error", extra={
                "operation": "add", "doc_id": doc_id, "error": str(e)
            })
            return {"status": "error", "enterprise": enterprise, "error": f"向量写入失败: {e}"}

        # 5. MinIO 存储（best-effort）
        minio_path = None
        if self.minio:
            try:
                object_name = f"{enterprise}/{filename}"
                self.minio.upload_bytes(content_bytes, object_name)
                minio_path = object_name
            except Exception as e:
                logger.warning("rag.minio.warning", extra={
                    "object": f"{enterprise}/{filename}", "error": str(e)
                })

        # 6. 标记文档为 active + 更新企业计数
        self.repo.mark_document_active(doc_id, len(chunks), minio_path)
        self.repo.increment_enterprise(enterprise, 1, len(chunks))

        logger.info("rag.upload.complete", extra={
            "doc_id": doc_id, "chunks": len(chunks), "minio": minio_path
        })

        return {
            "status": "ok",
            "enterprise": enterprise,
            "filename": filename,
            "doc_id": doc_id,
            "chunks": len(chunks),
            "minio_path": minio_path,
        }

    # ── 列表 ──

    def list_enterprises(self) -> list[dict]:
        """从 MySQL 读企业列表，不依赖 ChromaDB"""
        return self.repo.list_enterprises()

    def get_documents(self, enterprise: str) -> list[dict]:
        """获取某企业的所有文档"""
        return self.repo.get_documents(enterprise)

    # ── 删除 ──

    def delete_enterprise(self, name: str) -> dict:
        """联动删除：ChromaDB → MinIO → MySQL"""
        # 1. 收集 doc_ids
        doc_ids = self.repo.get_doc_ids_for_enterprise(name)

        # 2. 删除 ChromaDB 向量
        if doc_ids:
            self.chroma.delete_by_docs(doc_ids)

        # 3. 删除 MinIO 文件（best-effort）
        if self.minio:
            try:
                self.minio.delete_object(prefix=f"{name}/")
            except Exception:
                pass

        # 4. 删除 MySQL 记录（CASCADE 自动清 rag_documents）
        self.repo.delete_enterprise(name)

        return {"status": "ok", "enterprise": name}

    # ── 查询 ──

    def query(self, field_key: str, enterprise: str = "", n_results: int = 3) -> str:
        """语义检索"""
        return self.chroma.query(field_key, enterprise, n_results)

    # ── 健康 ──

    def health(self) -> dict:
        """健康探针"""
        mysql_ok = self.repo.db.health()
        chroma_ok, chroma_msg = self.chroma.health()

        return {
            "mysql": "ok" if mysql_ok else "down",
            "chromadb": "ok" if chroma_ok else f"down: {chroma_msg}",
            "embedding": "ok" if chroma_ok else "unknown",
        }

    # ── 内部工具 ──

    @staticmethod
    def _extract_text(content: bytes, filename: str) -> str:
        """根据文件后缀提取文本"""
        name = filename.lower()
        if name.endswith(".docx"):
            from docx import Document
            doc = Document(BytesIO(content))
            return "\n".join(p.text for p in doc.paragraphs)
        elif name.endswith(".pdf"):
            from pypdf import PdfReader
            reader = PdfReader(BytesIO(content))
            return "\n".join(page.extract_text() or "" for page in reader.pages)
        else:
            return content.decode("utf-8", errors="replace")
