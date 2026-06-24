"""向量数据库 RAG：上传 → 分块 → 嵌入 → 检索"""

from __future__ import annotations

import os
from pathlib import Path

import chromadb
from chromadb.utils import embedding_functions

CHUNK_SIZE = 300
COLLECTION_NAME = "enterprise_refs"

_client: chromadb.ClientAPI | None = None
_collection: chromadb.Collection | None = None


def _get_collection() -> chromadb.Collection | None:
    global _client, _collection
    if _collection is None:
        try:
            db_dir = os.getenv("CHROMA_DB_DIR", str(Path(__file__).resolve().parent.parent.parent / "chroma_db"))
            _client = chromadb.PersistentClient(path=db_dir)
            os.environ.setdefault("HF_ENDPOINT", "https://hf-mirror.com")
            ef = embedding_functions.SentenceTransformerEmbeddingFunction(
                model_name="all-MiniLM-L6-v2"
            )
            _collection = _client.get_or_create_collection(
                name=COLLECTION_NAME, embedding_function=ef
            )
        except Exception as e:
            import logging
            logging.getLogger(__name__).warning("ChromaDB init failed: %s", e)
            return None
    return _collection


def upload_file(file_path: str, enterprise: str) -> dict:
    """上传文件：读取 → 分块 → 嵌入 → 存入向量库。"""
    with open(file_path, "r", encoding="utf-8") as f:
        text = f.read()
    source = os.path.basename(file_path)
    chunks = _chunk_text(text)
    source_key = source.replace(".", "_")
    ids = [f"{enterprise}_{source_key}_{i}" for i in range(len(chunks))]
    metadatas = [{"enterprise": enterprise, "source": source}] * len(chunks)
    col = _get_collection()
    # 仅清除同源文件旧数据
    try:
        col.delete(where={"$and": [{"enterprise": enterprise}, {"source": source}]})
    except Exception:
        pass
    if chunks:
        col.add(documents=chunks, ids=ids, metadatas=metadatas)
    return {"enterprise": enterprise, "chunks": len(chunks)}


def upload_text(content: str, enterprise: str, source: str = "manual") -> dict:
    """直接上传文本内容（用于网页粘贴上传）。"""
    chunks = _chunk_text(content)
    source_key = source.replace(".", "_")
    ids = [f"{enterprise}_{source_key}_{i}" for i in range(len(chunks))]
    metadatas = [{"enterprise": enterprise, "source": source}] * len(chunks)
    col = _get_collection()
    # 仅清除同源文件旧数据
    try:
        col.delete(where={"$and": [{"enterprise": enterprise}, {"source": source}]})
    except Exception:
        pass
    if chunks:
        col.add(documents=chunks, ids=ids, metadatas=metadatas)
    return {"enterprise": enterprise, "chunks": len(chunks)}


def query(field_key: str, enterprise: str = "", n_results: int = 3) -> str:
    """检索最相关文档块。field_key 转为自然语言查询。不指定 enterprise 则搜索全部。"""
    col = _get_collection()
    if col is None:
        return ""  # ChromaDB 不可用时返回空
    query_text = field_key.replace("_", " ")
    where = {"enterprise": enterprise} if enterprise else None
    try:
        results = col.query(
            query_texts=[query_text],
            n_results=n_results,
            where=where,
        )
    except Exception:
        return ""
    docs = results.get("documents", [[]])[0]
    return "\n".join(docs) if docs else ""


def list_enterprises() -> list[str]:
    """列出已上传的企业。"""
    col = _get_collection()
    try:
        results = col.get()
        return sorted(set(
            m.get("enterprise", "") for m in (results.get("metadatas") or [])
        ))
    except Exception:
        return []


def delete_enterprise(enterprise: str) -> None:
    """删除某企业的所有向量数据。"""
    col = _get_collection()
    try:
        col.delete(where={"enterprise": enterprise})
    except Exception:
        pass


def _chunk_text(text: str) -> list[str]:
    """按段落分块，每块不超过 CHUNK_SIZE 字符。"""
    paragraphs = [p.strip() for p in text.split("\n\n") if p.strip()]
    chunks: list[str] = []
    current = ""
    for para in paragraphs:
        if len(current) + len(para) > CHUNK_SIZE:
            if current:
                chunks.append(current)
            current = para
        else:
            current = (current + "\n\n" + para) if current else para
    if current:
        chunks.append(current)
    return chunks
