"""ChromaDB 向量存储 — 仅负责存向量、查向量、删向量"""
from __future__ import annotations

import os
from pathlib import Path

import chromadb


class ChromaStore:
    """ChromaDB 向量存储封装"""

    def __init__(
        self,
        embedding_engine=None,
        collection_name: str = "enterprise_refs",
        db_dir: str | None = None,
    ):
        self.embedding_engine = embedding_engine
        self.collection_name = collection_name
        if db_dir is None:
            db_dir = os.getenv(
                "CHROMA_DB_DIR",
                str(Path(__file__).resolve().parent.parent.parent / "chroma_db"),
            )
        self._client = chromadb.PersistentClient(path=db_dir)
        self._col = self._client.get_or_create_collection(
            name=collection_name,
            embedding_function=embedding_engine.embedding_function if embedding_engine else None,
        )

    # ── 写入 ──

    def add_chunks(self, chunks: list[str], enterprise: str, doc_id: int) -> int:
        """写入分块向量。返回写入的 chunk 数量"""
        if not chunks:
            return 0
        ids = [f"doc_{doc_id}_chunk_{i}" for i in range(len(chunks))]
        metadatas = [
            {"enterprise": enterprise, "doc_id": doc_id, "chunk_idx": i}
            for i in range(len(chunks))
        ]
        self._col.add(documents=chunks, ids=ids, metadatas=metadatas)
        return len(chunks)

    # ── 查询 ──

    def query(self, field_key: str, enterprise: str = "", n_results: int = 3) -> str:
        """语义检索，返回拼接后的文档块文本"""
        query_text = field_key.replace("_", " ")
        where = {"enterprise": enterprise} if enterprise else None
        try:
            results = self._col.query(
                query_texts=[query_text],
                n_results=n_results,
                where=where,
            )
        except Exception:
            return ""
        docs = results.get("documents", [[]])[0]
        return "\n".join(docs) if docs else ""

    # ── 删除 ──

    def delete_by_doc(self, doc_id: int) -> None:
        """按 doc_id 删除一个文档的所有向量块"""
        try:
            self._col.delete(where={"doc_id": doc_id})
        except Exception:
            pass

    def delete_by_docs(self, doc_ids: list[int]) -> None:
        """按 doc_id 列表批量删除"""
        for did in doc_ids:
            self.delete_by_doc(did)

    def delete_by_enterprise(self, enterprise: str) -> None:
        """按企业名删除所有向量"""
        try:
            self._col.delete(where={"enterprise": enterprise})
        except Exception:
            pass

    # ── 运维 ──

    def health(self) -> tuple[bool, str]:
        """健康探针"""
        try:
            self._col.count()
            return True, "ok"
        except Exception as e:
            return False, str(e)

    def count(self) -> int:
        """返回总 chunk 数"""
        return self._col.count()

    # ── 数据迁移用 ──

    def get_all_metadata(self) -> list[dict]:
        """获取所有 chunk 的 metadata（迁移用），不分页，适合中小规模"""
        result = self._col.get()
        return result.get("metadatas") or []
