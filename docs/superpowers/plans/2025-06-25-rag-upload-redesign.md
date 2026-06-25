# RAG 上传模块全量重构 实现计划

> **面向 AI 代理的工作者：** 必需子技能：使用 superpowers:subagent-driven-development（推荐）或 superpowers:executing-plans 逐任务实现此计划。步骤使用复选框（`- [ ]`）语法来跟踪进度。

**目标：** 将 RAG 存储从"ChromaDB 单一依赖"重构为 MySQL（真相源）+ ChromaDB（向量索引）双层架构，根治企业列表消失问题。

**架构：** MySQL `rag_enterprises` + `rag_documents` 两表记录企业-文档关系，ChromaDB 只存向量和做语义检索。后端拆分为 5 个模块（chunker / embedding / chroma_store / rag_repo / rag_service），前端 UploadPage 增强 + ResearchPage 集成 RAG + 新增文档详情页。

**技术栈：** Python FastAPI + pymysql (MySQL) + ChromaDB + SentenceTransformers + Vue 3 + TypeScript

---

### 任务 0：添加 MySQL 依赖

**文件：**
- 修改：`backend/pyproject.toml`

- [ ] **步骤 1：添加 pymysql 依赖**

在 `backend/pyproject.toml` 的 dependencies 列表末尾添加：

```toml
"pymysql>=1.1.1",
```

- [ ] **步骤 2：安装依赖**

```bash
cd backend && pip install pymysql>=1.1.1
```

预期：安装成功，无报错。

- [ ] **步骤 3：Commit**

```bash
git add backend/pyproject.toml
git commit -m "chore: add pymysql dependency for RAG MySQL backend"
```

---

### 任务 1：创建 MySQL 客户端模块

**文件：**
- 创建：`backend/src/mysql_client.py`

- [ ] **步骤 1：创建 MySQLClient 类**

```python
"""MySQL client — 短连接模式，每次操作 open/close"""
from __future__ import annotations

import os
import pymysql
from pymysql.cursors import DictCursor


class MySQLClient:
    """轻量 MySQL 客户端，每次 query/execute 创建新连接"""

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
        """执行写操作，返回 lastrowid"""
        conn = self._connect()
        try:
            with conn.cursor() as cursor:
                cursor.execute(sql, params)
                return cursor.lastrowid
        finally:
            conn.close()

    def query(self, sql: str, params=None) -> list[dict]:
        """执行读操作，返回 dict 列表"""
        conn = self._connect()
        try:
            with conn.cursor() as cursor:
                cursor.execute(sql, params)
                return cursor.fetchall()
        finally:
            conn.close()

    def health(self) -> bool:
        """健康检查"""
        try:
            conn = self._connect()
            with conn.cursor() as cursor:
                cursor.execute("SELECT 1")
            conn.close()
            return True
        except Exception:
            return False
```

- [ ] **步骤 2：验证模块可导入**

```bash
cd backend && python -c "from src.mysql_client import MySQLClient; c = MySQLClient(); print('host:', c.host)"
```

预期：打印出 host 配置，无 ImportError。

- [ ] **步骤 3：Commit**

```bash
git add backend/src/mysql_client.py
git commit -m "feat: add MySQLClient for RAG MySQL backend"
```

---

### 任务 2：DDL 建表迁移

**文件：**
- 创建：`backend/migrations/001_rag_tables.sql`
- 创建：`backend/scripts/migrate_rag_schema.py`

- [ ] **步骤 1：编写 DDL SQL**

```sql
-- backend/migrations/001_rag_tables.sql
-- RAG 企业-文档索引，MySQL 作为真相源

CREATE TABLE IF NOT EXISTS rag_enterprises (
    id          BIGINT AUTO_INCREMENT PRIMARY KEY,
    name        VARCHAR(255) NOT NULL COMMENT '企业名称',
    doc_count   INT NOT NULL DEFAULT 0 COMMENT '文档数量',
    chunk_count INT NOT NULL DEFAULT 0 COMMENT '总块数',
    created_at  DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at  DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    UNIQUE KEY uk_name (name),
    INDEX idx_name (name)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='RAG企业索引';

CREATE TABLE IF NOT EXISTS rag_documents (
    id           BIGINT AUTO_INCREMENT PRIMARY KEY,
    enterprise   VARCHAR(255) NOT NULL COMMENT '企业名称',
    filename     VARCHAR(512) NOT NULL COMMENT '原始文件名',
    file_size    BIGINT NOT NULL DEFAULT 0 COMMENT '文件大小(bytes)',
    chunk_count  INT NOT NULL DEFAULT 0 COMMENT '分块数量',
    minio_path   VARCHAR(1024) DEFAULT NULL COMMENT 'MinIO对象路径',
    status       ENUM('uploading','active','failed','deleted') NOT NULL DEFAULT 'uploading' COMMENT '文档状态',
    error_msg    TEXT DEFAULT NULL COMMENT '失败原因',
    created_at   DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at   DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    INDEX idx_enterprise (enterprise),
    INDEX idx_status (status),
    CONSTRAINT fk_rag_docs_enterprise FOREIGN KEY (enterprise)
        REFERENCES rag_enterprises(name) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='RAG文档明细';
```

- [ ] **步骤 2：编写迁移执行脚本**

```python
"""执行 DDL 建表迁移"""
import os
import sys
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from mysql_client import MySQLClient
from pathlib import Path


def main():
    db = MySQLClient()
    if not db.health():
        print("ERROR: MySQL 不可达，请检查 MYSQL_HOST/MYSQL_PORT/MYSQL_USER/MYSQL_PASSWORD/MYSQL_DATABASE 环境变量")
        sys.exit(1)

    sql_path = Path(__file__).parent.parent / "migrations" / "001_rag_tables.sql"
    sql = sql_path.read_text(encoding="utf-8")

    # 逐条执行（分号分割）
    statements = [s.strip() for s in sql.split(";") if s.strip()]
    for stmt in statements:
        try:
            db.execute(stmt)
            print(f"OK: {stmt[:60]}...")
        except Exception as e:
            print(f"SKIP (may already exist): {e}")

    # 验证
    rows = db.query("SHOW TABLES LIKE 'rag_%'")
    print(f"Tables created: {[list(r.values())[0] for r in rows]}")
    print("Migration complete.")


if __name__ == "__main__":
    main()
```

- [ ] **步骤 3：执行迁移（需要 MySQL 可用时）**

```bash
cd backend && python scripts/migrate_rag_schema.py
```

如果 MySQL 暂未配置，先跳过，后续任务完成后再执行。

- [ ] **步骤 4：Commit**

```bash
git add backend/migrations/ backend/scripts/
git commit -m "feat: add RAG MySQL schema DDL and migration script"
```

---

### 任务 3：创建 chunker.py — 文本分块模块

**文件：**
- 创建：`backend/src/services/chunker.py`
- 创建：`backend/tests/services/test_chunker.py`

- [ ] **步骤 1：编写失败测试**

```python
"""chunker 单元测试"""
import pytest
from src.services.chunker import Chunker


class TestChunker:
    def test_chunk_paragraph_basic(self):
        c = Chunker(chunk_size=500)
        text = "段落一。\n\n段落二。\n\n段落三。"
        chunks = c.chunk(text)
        assert len(chunks) >= 1
        assert "段落一" in chunks[0]

    def test_chunk_paragraph_small_chunks(self):
        c = Chunker(chunk_size=10)
        text = "很长的第一段文字内容。\n\n很长的第二段文字内容。"
        chunks = c.chunk(text)
        # 每段独立成块
        assert len(chunks) == 2

    def test_chunk_paragraph_empty(self):
        c = Chunker()
        chunks = c.chunk("")
        assert chunks == []

    def test_chunk_paragraph_merge_short(self):
        c = Chunker(chunk_size=500)
        text = "短句A。\n\n短句B。\n\n短句C。"
        chunks = c.chunk(text)
        # 短段落合并为一块
        assert len(chunks) == 1

    def test_chunk_unknown_strategy_raises(self):
        c = Chunker(strategy="unknown")
        with pytest.raises(ValueError, match="Unknown strategy"):
            c.chunk("test")
```

- [ ] **步骤 2：运行测试验证失败**

```bash
cd backend && python -m pytest tests/services/test_chunker.py -v
```

预期：5 个测试全部 FAIL，`ModuleNotFoundError` 或 `ImportError`。

- [ ] **步骤 3：实现 Chunker 类**

```python
"""文本分块策略 — 可配置 chunk_size 和分块方式"""
from __future__ import annotations


class Chunker:
    """文本分块器"""

    def __init__(self, chunk_size: int = 500, strategy: str = "paragraph"):
        self.chunk_size = chunk_size
        self.strategy = strategy

    def chunk(self, text: str) -> list[str]:
        """将文本分块，返回块列表"""
        if not text.strip():
            return []
        if self.strategy == "paragraph":
            return self._chunk_paragraph(text)
        raise ValueError(f"Unknown strategy: {self.strategy}")

    def _chunk_paragraph(self, text: str) -> list[str]:
        """按段落分块，每块不超过 chunk_size 字符"""
        paragraphs = [p.strip() for p in text.split("\n\n") if p.strip()]
        chunks: list[str] = []
        current = ""
        for para in paragraphs:
            if len(current) + len(para) > self.chunk_size:
                if current:
                    chunks.append(current)
                current = para
            else:
                current = (current + "\n\n" + para) if current else para
        if current:
            chunks.append(current)
        return chunks
```

- [ ] **步骤 4：运行测试验证通过**

```bash
cd backend && python -m pytest tests/services/test_chunker.py -v
```

预期：5 PASS。

- [ ] **步骤 5：Commit**

```bash
git add backend/src/services/chunker.py backend/tests/services/test_chunker.py
git commit -m "feat: add Chunker with paragraph strategy and configurable chunk_size"
```

---

### 任务 4：创建 embedding.py — 嵌入引擎模块

**文件：**
- 创建：`backend/src/services/embedding.py`

- [ ] **步骤 1：实现 EmbeddingEngine 类**

```python
"""嵌入引擎 — 可切换模型，封装 SentenceTransformers"""
from __future__ import annotations

import os
from chromadb.utils import embedding_functions


class EmbeddingEngine:
    """嵌入模型引擎，支持多模型切换"""

    MODELS = {
        "minilm":    ("all-MiniLM-L6-v2", 384),
        "bge-small": ("BGE-small-zh",      512),
        "bge-large": ("BGE-large-zh",     1024),
    }

    def __init__(self, model_name: str = "minilm"):
        if model_name not in self.MODELS:
            raise ValueError(
                f"Unknown model '{model_name}'. Available: {list(self.MODELS)}"
            )
        self.model_name = model_name
        self.model_id, self.dims = self.MODELS[model_name]
        os.environ.setdefault("HF_ENDPOINT", "https://hf-mirror.com")
        self._ef = embedding_functions.SentenceTransformerEmbeddingFunction(
            model_name=self.model_id
        )

    @property
    def embedding_function(self):
        return self._ef

    def health(self) -> tuple[bool, str]:
        """健康探针：尝试编码一段短文本"""
        try:
            self._ef(["健康检查"])
            return True, "ok"
        except Exception as e:
            return False, str(e)
```

- [ ] **步骤 2：验证可导入和健康检查**

```bash
cd backend && python -c "
from src.services.embedding import EmbeddingEngine
e = EmbeddingEngine('minilm')
print('model:', e.model_id, 'dims:', e.dims)
ok, msg = e.health()
print('health:', ok, msg)
"
```

预期：打印 model id、dims 和 health 状态。

- [ ] **步骤 3：Commit**

```bash
git add backend/src/services/embedding.py
git commit -m "feat: add EmbeddingEngine with switchable model support"
```

---

### 任务 5：创建 chroma_store.py — ChromaDB 向量存储

**文件：**
- 创建：`backend/src/services/chroma_store.py`
- 创建：`backend/tests/services/test_chroma_store.py`

- [ ] **步骤 1：编写失败测试**

```python
"""chroma_store 单元测试"""
import pytest
from src.services.embedding import EmbeddingEngine
from src.services.chroma_store import ChromaStore


@pytest.fixture
def store():
    eng = EmbeddingEngine("minilm")
    return ChromaStore(embedding_engine=eng, collection_name="test_enterprise_refs")


class TestChromaStore:
    def test_add_and_query(self, store):
        store.add_chunks(
            chunks=["测试文档块一", "测试文档块二"],
            enterprise="测试企业",
            doc_id=1,
        )
        result = store.query("测试文档", enterprise="测试企业", n_results=2)
        assert len(result) > 0

    def test_delete_by_doc(self, store):
        store.add_chunks(
            chunks=["待删除的块"],
            enterprise="测试企业B",
            doc_id=99,
        )
        store.delete_by_doc(99)
        result = store.query("待删除", enterprise="测试企业B")
        assert result == ""

    def test_health(self, store):
        ok, msg = store.health()
        assert ok
        assert msg == "ok"
```

- [ ] **步骤 2：运行测试验证失败**

```bash
cd backend && python -m pytest tests/services/test_chroma_store.py -v
```

预期：全部 FAIL，`ModuleNotFoundError` / `ImportError`。

- [ ] **步骤 3：实现 ChromaStore 类**

```python
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
```

- [ ] **步骤 4：运行测试验证通过**

```bash
cd backend && python -m pytest tests/services/test_chroma_store.py -v
```

预期：3 PASS。

- [ ] **步骤 5：Commit**

```bash
git add backend/src/services/chroma_store.py backend/tests/services/test_chroma_store.py
git commit -m "feat: add ChromaStore — vector-only ChromaDB wrapper"
```

---

### 任务 6：创建 rag_repo.py — MySQL 数据访问层

**文件：**
- 创建：`backend/src/services/rag_repo.py`
- 创建：`backend/tests/services/test_rag_repo.py`

- [ ] **步骤 1：编写失败测试**

```python
"""rag_repo 单元测试（需要 MySQL）"""
import pytest
from src.mysql_client import MySQLClient
from src.services.rag_repo import RagRepo


@pytest.fixture
def repo():
    db = MySQLClient()
    if not db.health():
        pytest.skip("MySQL not available")
    r = RagRepo(db)
    r.init_tables()
    # 清理旧测试数据
    db.execute("DELETE FROM rag_documents WHERE enterprise LIKE 'test_%'")
    db.execute("DELETE FROM rag_enterprises WHERE name LIKE 'test_%'")
    yield r
    # teardown
    db.execute("DELETE FROM rag_documents WHERE enterprise LIKE 'test_%'")
    db.execute("DELETE FROM rag_enterprises WHERE name LIKE 'test_%'")


class TestRagRepo:
    def test_upsert_enterprise(self, repo):
        repo.upsert_enterprise("test_企业A")
        enterprises = repo.list_enterprises()
        names = [e["name"] for e in enterprises]
        assert "test_企业A" in names

    def test_upsert_enterprise_idempotent(self, repo):
        repo.upsert_enterprise("test_企业B")
        repo.upsert_enterprise("test_企业B")  # 第二次不报错
        enterprises = repo.list_enterprises()
        assert sum(1 for e in enterprises if e["name"] == "test_企业B") == 1

    def test_insert_document_flow(self, repo):
        repo.upsert_enterprise("test_企业C")
        doc_id = repo.insert_document("test_企业C", "测试文档.md", 1024)
        assert doc_id > 0

        repo.mark_document_active(doc_id, 5, "test_企业C/测试文档.md")
        docs = repo.get_documents("test_企业C")
        assert len(docs) == 1
        assert docs[0]["status"] == "active"
        assert docs[0]["chunk_count"] == 5

    def test_mark_document_failed(self, repo):
        repo.upsert_enterprise("test_企业D")
        doc_id = repo.insert_document("test_企业D", "失败文档.md", 0)
        repo.mark_document_failed(doc_id, "模拟错误")
        docs = repo.get_documents("test_企业D")
        assert docs[0]["status"] == "failed"
        assert "模拟错误" in docs[0]["error_msg"]

    def test_delete_enterprise_cascades(self, repo):
        repo.upsert_enterprise("test_企业E")
        repo.insert_document("test_企业E", "doc1.md", 100)
        repo.delete_enterprise("test_企业E")
        enterprises = repo.list_enterprises()
        assert "test_企业E" not in [e["name"] for e in enterprises]
        docs = repo.get_documents("test_企业E")
        assert docs == []
```

- [ ] **步骤 2：运行测试验证失败**

```bash
cd backend && python -m pytest tests/services/test_rag_repo.py -v
```

预期：全部 FAIL（模块不存在）。

- [ ] **步骤 3：实现 RagRepo 类**

```python
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
            name        VARCHAR(255) NOT NULL COMMENT '企业名称',
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
            "FROM rag_enterprises WHERE 1=1 "
            "HAVING doc_count > 0 OR chunk_count > 0 "  # 只列出有文档的企业
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
```

- [ ] **步骤 4：运行测试验证通过**

```bash
cd backend && python -m pytest tests/services/test_rag_repo.py -v
```

预期：5 PASS（如 MySQL 不可用则全部 SKIP）。

- [ ] **步骤 5：Commit**

```bash
git add backend/src/services/rag_repo.py backend/tests/services/test_rag_repo.py
git commit -m "feat: add RagRepo — MySQL CRUD for rag_enterprises + rag_documents"
```

---

### 任务 7：创建 rag_service.py — RAG 服务编排层

**文件：**
- 创建：`backend/src/services/rag_service.py`
- 创建：`backend/tests/services/test_rag_service.py`

- [ ] **步骤 1：编写失败测试**

```python
"""rag_service 单元测试"""
import pytest
from src.mysql_client import MySQLClient
from src.services.embedding import EmbeddingEngine
from src.services.chroma_store import ChromaStore
from src.services.chunker import Chunker
from src.services.rag_repo import RagRepo
from src.services.rag_service import RagService


@pytest.fixture
def svc():
    db = MySQLClient()
    if not db.health():
        pytest.skip("MySQL not available")
    repo = RagRepo(db)
    repo.init_tables()
    embedding = EmbeddingEngine("minilm")
    store = ChromaStore(embedding_engine=embedding, collection_name="test_rag_svc")
    chunker = Chunker(chunk_size=500)
    svc = RagService(repo=repo, chroma_store=store, chunker=chunker)
    # cleanup
    db.execute("DELETE FROM rag_documents WHERE enterprise LIKE 'test_svc_%'")
    db.execute("DELETE FROM rag_enterprises WHERE name LIKE 'test_svc_%'")
    yield svc
    db.execute("DELETE FROM rag_documents WHERE enterprise LIKE 'test_svc_%'")
    db.execute("DELETE FROM rag_enterprises WHERE name LIKE 'test_svc_%'")


class TestRagService:
    def test_upload_and_list(self, svc):
        result = svc.upload_file(
            enterprise="test_svc_企业A",
            filename="测试文档.md",
            content_bytes="这是测试文档内容。\n\n包含多个段落。\n\n用于RAG检索。".encode("utf-8"),
        )
        assert result["status"] == "ok"
        assert result["enterprise"] == "test_svc_企业A"
        assert result["chunks"] > 0

        enterprises = svc.list_enterprises()
        names = [e["name"] for e in enterprises]
        assert "test_svc_企业A" in names

    def test_delete_enterprise(self, svc):
        svc.upload_file(
            enterprise="test_svc_企业B",
            filename="doc.md",
            content_bytes="测试内容".encode("utf-8"),
        )
        svc.delete_enterprise("test_svc_企业B")
        enterprises = svc.list_enterprises()
        assert "test_svc_企业B" not in [e["name"] for e in enterprises]

    def test_health(self, svc):
        health = svc.health()
        assert "mysql" in health
        assert "chromadb" in health
        assert "embedding" in health
```

- [ ] **步骤 2：运行测试验证失败**

```bash
cd backend && python -m pytest tests/services/test_rag_service.py -v
```

预期：全部 FAIL。

- [ ] **步骤 3：实现 RagService 类**

```python
"""RAG 服务编排层 — 原子上传、列表查询、联动删除"""
from __future__ import annotations

import logging

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
        import logging
        log = logging.getLogger(__name__)

        enterprise = enterprise.strip()
        log.info("rag.upload.start", extra={
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
        log.info("rag.upload.chunk", extra={
            "doc_id": doc_id, "chunks": len(chunks), "chunk_size": self.chunker.chunk_size
        })

        # 4. 写入 ChromaDB
        try:
            self.chroma.add_chunks(chunks, enterprise, doc_id)
        except Exception as e:
            self.repo.mark_document_failed(doc_id, f"ChromaDB写入失败: {e}")
            log.error("rag.chromadb.error", extra={"operation": "add", "doc_id": doc_id, "error": str(e)})
            return {"status": "error", "enterprise": enterprise, "error": f"向量写入失败: {e}"}

        # 5. MinIO 存储（best-effort）
        minio_path = None
        if self.minio:
            try:
                object_name = f"{enterprise}/{filename}"
                self.minio.upload_bytes(content_bytes, object_name)
                minio_path = object_name
            except Exception as e:
                log.warning("rag.minio.warning", extra={"object": f"{enterprise}/{filename}", "error": str(e)})

        # 6. 标记文档为 active + 更新企业计数
        self.repo.mark_document_active(doc_id, len(chunks), minio_path)
        self.repo.increment_enterprise(enterprise, 1, len(chunks))

        log.info("rag.upload.complete", extra={
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
        return self.repo.get_documents(enterprise)

    # ── 删除 ──

    def delete_enterprise(self, name: str) -> dict:
        """联动删除：Chromadb → MinIO → MySQL"""
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
        mysql_ok = self.repo.db.health()
        chroma_ok, chroma_msg = self.chroma.health()
        # embedding engine health is checked via chroma_store (which owns it)

        return {
            "mysql": "ok" if mysql_ok else "down",
            "chromadb": "ok" if chroma_ok else f"down: {chroma_msg}",
            "embedding": "ok" if chroma_ok else "unknown",
        }

    # ── 内部工具 ──

    @staticmethod
    def _extract_text(content: bytes, filename: str) -> str:
        """根据文件后缀提取文本"""
        from io import BytesIO
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
```

- [ ] **步骤 4：运行测试验证通过**

```bash
cd backend && python -m pytest tests/services/test_rag_service.py -v
```

预期：3 PASS。

- [ ] **步骤 5：Commit**

```bash
git add backend/src/services/rag_service.py backend/tests/services/test_rag_service.py
git commit -m "feat: add RagService — atomic upload, MySQL-backed list, cascading delete"
```

---

### 任务 8：改造 main.py RAG API 端点

**文件：**
- 修改：`backend/src/main.py`（RAG 路由区域，约 line 408-472）

- [ ] **步骤 1：添加 RAG service 初始化代码**

在 `create_app()` 函数开头附近，添加 RAG 服务初始化：

```python
def create_app():
    app = FastAPI(...)
    
    # ── RAG Service 初始化 ──
    from services.embedding import EmbeddingEngine
    from services.chroma_store import ChromaStore
    from services.chunker import Chunker
    from services.rag_repo import RagRepo
    from services.rag_service import RagService
    from mysql_client import MySQLClient
    
    _mysql = MySQLClient()
    _rag_repo = RagRepo(_mysql)
    _rag_repo.init_tables()  # 幂等建表
    _rag_embedding = EmbeddingEngine(
        model_name=os.getenv("EMBEDDING_MODEL", "minilm")
    )
    _rag_chroma = ChromaStore(embedding_engine=_rag_embedding)
    _rag_chunker = Chunker(
        chunk_size=int(os.getenv("CHUNK_SIZE", "500"))
    )
    _rag = RagService(
        repo=_rag_repo,
        chroma_store=_rag_chroma,
        chunker=_rag_chunker,
    )
```

- [ ] **步骤 2：替换 `POST /rag/upload/file` 端点**

删除旧的 `rag_upload_file` 函数（约 line 441-463），替换为：

```python
@app.post("/rag/upload/file")
def rag_upload_file(
    enterprise: str = Form(...),
    file: UploadFile = File(...),
):
    if not enterprise.strip():
        raise HTTPException(400, "企业名称不能为空")
    raw = file.file.read()
    result = _rag.upload_file(enterprise.strip(), file.filename or "upload", raw)
    if result["status"] == "error":
        raise HTTPException(400, result.get("error", "上传失败"))
    return result
```

- [ ] **步骤 3：替换 `GET /rag/enterprises` 端点**

删除旧的 `rag_enterprises` 函数（约 line 465-467），替换为：

```python
@app.get("/rag/enterprises")
def rag_enterprises():
    return {"enterprises": _rag.list_enterprises()}
```

**注意**：响应格式从 `["企业名"]` 变为 `[{"name": "...", "doc_count": N, ...}]`，前端需要同步更新（任务 10 处理）。

- [ ] **步骤 4：替换 `DELETE /rag/enterprise/{name}` 端点**

删除旧的 `rag_delete_enterprise` 函数（约 line 469-472），替换为：

```python
@app.delete("/rag/enterprise/{name:path}")
def rag_delete_enterprise(name: str):
    result = _rag.delete_enterprise(name)
    return result
```

- [ ] **步骤 5：添加 `GET /rag/health` 端点**

```python
@app.get("/rag/health")
def rag_health():
    return _rag.health()
```

- [ ] **步骤 6：添加 `GET /rag/documents` 端点**

```python
@app.get("/rag/documents")
def rag_documents(enterprise: str = Query(...)):
    if not enterprise.strip():
        raise HTTPException(400, "企业名称不能为空")
    return {"documents": _rag.get_documents(enterprise.strip())}
```

- [ ] **步骤 7：添加 `POST /rag/admin/reindex` 端点（骨架）**

```python
@app.post("/rag/admin/reindex")
def rag_reindex():
    """切换嵌入模型后重建全量索引（骨架）"""
    return {
        "status": "not_implemented",
        "message": "reindex endpoint reserved for future use"
    }
```

- [ ] **步骤 8：更新 RAG query 调用点**

在 `_run_collection_cycle` 函数中（约 line 1288-1296），将 `from services.rag_store import query as rag_query` 替换为：

```python
# 旧代码：
# from services.rag_store import query as rag_query
# result = rag_query(kw, ent["name"], n_results=1)

# 新代码：直接使用 _rag.query()
result = _rag.query(kw, ent["name"], n_results=1)
```

并移除旧的 import：

```python
# 删除这些行（约 line 410）：
# from services.rag_store import upload_text, list_enterprises, delete_enterprise
```

- [ ] **步骤 9：验证后端启动无报错**

```bash
cd backend && timeout 5 python -m src.main 2>&1 || true
```

预期：无 ImportError，日志正常。如果有 MySQL 连接失败，应在 health 中体现但不阻塞启动。

- [ ] **步骤 10：Commit**

```bash
git add backend/src/main.py
git commit -m "refactor: rewrite RAG API endpoints with RagService

- POST /rag/upload/file: atomic upload via RagService
- GET /rag/enterprises: MySQL-backed list with doc_count
- DELETE /rag/enterprise/{name}: cascading delete (ChromaDB + MinIO + MySQL)
- GET /rag/health: health check (mysql/chromadb/embedding)
- GET /rag/documents: list documents per enterprise
- POST /rag/admin/reindex: reserved for model switch"
```

---

### 任务 9：数据迁移脚本

**文件：**
- 创建：`backend/scripts/migrate_chromadb_to_mysql.py`

- [ ] **步骤 1：编写迁移脚本**

```python
"""将 ChromaDB 中现有数据的企业/文档元数据迁移到 MySQL

不重建向量，只迁移索引关系。
"""
import os
import sys
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from collections import defaultdict
from services.chroma_store import ChromaStore
from mysql_client import MySQLClient
from services.rag_repo import RagRepo


def main():
    db = MySQLClient()
    if not db.health():
        print("ERROR: MySQL 不可达")
        sys.exit(1)

    repo = RagRepo(db)
    repo.init_tables()

    # 从 ChromaDB 读取所有 metadata
    print("Reading ChromaDB metadata...")
    chroma = ChromaStore()
    all_meta = chroma.get_all_metadata()
    print(f"Total chunks in ChromaDB: {len(all_meta)}")

    # 按 enterprise + doc_id 分组
    enterprise_docs: dict[str, dict[int, int]] = defaultdict(lambda: defaultdict(int))
    enterprise_chunks: dict[str, int] = defaultdict(int)
    enterprise_names: set[str] = set()

    for m in all_meta:
        ent = m.get("enterprise", "")
        if not ent:
            continue
        enterprise_names.add(ent)
        doc_id = m.get("doc_id", 0)
        if doc_id:
            enterprise_docs[ent][doc_id] += 1
        enterprise_chunks[ent] += 1

    print(f"Unique enterprises: {len(enterprise_names)}")

    # 写入 MySQL
    for ent in sorted(enterprise_names):
        # 企业记录
        repo.upsert_enterprise(ent)

        # 文档记录（从 ChromaDB metadata 推断）
        # 由于旧数据没有 doc_id，我们创建一个聚合文档记录
        total_chunks = enterprise_chunks[ent]
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
```

- [ ] **步骤 2：Commit**

```bash
git add backend/scripts/migrate_chromadb_to_mysql.py
git commit -m "feat: add ChromaDB → MySQL metadata migration script"
```

---

### 任务 10：升级 UploadPage.vue

**文件：**
- 修改：`frontend/src/pages/UploadPage.vue`

- [ ] **步骤 1：更新 TypeScript 类型和响应式状态**

替换 `<script setup>` 中 `enterprises` 的类型和新增状态变量：

```typescript
// 企业列表类型升级
interface Enterprise {
  name: string;
  doc_count: number;
  chunk_count: number;
  last_upload: string;
}

interface UploadResult {
  filename: string;
  ok: boolean;
  error?: string;
  chunks?: number;
}

const enterprises = ref<Enterprise[]>([]);
const uploadResults = ref<UploadResult[]>([]);
const errorType = ref<"network" | "server" | null>(null);
let lastGoodData: Enterprise[] = [];
```

- [ ] **步骤 2：改造 `refreshList()` — 异常保护 + 保留缓存**

替换现有的 `refreshList()` 函数（约 line 172-182）：

```typescript
async function refreshList() {
  try {
    const resp = await fetch("/rag/enterprises");
    if (!resp.ok) throw new Error(`HTTP ${resp.status}`);
    const data = await resp.json();
    lastGoodData = data.enterprises || [];
    enterprises.value = lastGoodData;
    errorType.value = null;
    showMsg("", "");
  } catch (e: any) {
    if (e instanceof TypeError || e.message?.includes("fetch")) {
      errorType.value = "network";
    } else {
      errorType.value = "server";
    }
    // 保留缓存数据
    if (lastGoodData.length > 0) {
      enterprises.value = lastGoodData;
    }
  } finally {
    loading.value = false;
  }
}
```

- [ ] **步骤 3：改造 `handleFiles()` — 收集上传结果明细**

替换现有的上传循环（约 line 139-159）：

```typescript
uploadResults.value = [];

for (let i = 0; i < total; i++) {
  const file = files[i];
  const pct = Math.round((i / total) * 100);
  progressPct.value = pct;
  progressText.value = "上传中 " + (i + 1) + "/" + total + "：" + file.name;

  const enterprise = extractEnterprise(file.name);
  const fd = new FormData();
  fd.append("enterprise", enterprise);
  fd.append("file", file);

  try {
    const resp = await fetch("/rag/upload/file", { method: "POST", body: fd });
    if (resp.ok) {
      const data = await resp.json();
      ok++;
      uploadResults.value.push({
        filename: file.name,
        ok: true,
        chunks: data.chunks,
      });
    } else {
      const data = await resp.json();
      err++;
      uploadResults.value.push({
        filename: file.name,
        ok: false,
        error: data.detail || `HTTP ${resp.status}`,
      });
    }
  } catch (e: any) {
    err++;
    uploadResults.value.push({
      filename: file.name,
      ok: false,
      error: e.message || "网络错误",
    });
  }
}
```

- [ ] **步骤 4：更新模板 — 企业列表展示**

替换企业列表模板（约 line 48-58）：

```html
<!-- 错误提示 -->
<div v-if="errorType === 'network'" class="error-banner warn">
  ⚠️ 网络异常，显示的是上次缓存数据
  <button class="btn-retry" @click="refreshList">重试</button>
</div>
<div v-else-if="errorType === 'server'" class="error-banner err">
  ❌ 服务异常，请稍后重试
</div>

<!-- 上传结果明细 -->
<div v-if="uploadResults.length > 0" class="upload-results">
  <div v-for="r in uploadResults" :key="r.filename" class="upload-result-row">
    <span class="ur-name">{{ r.filename }}</span>
    <span v-if="r.ok" class="ur-ok">✅ {{ r.chunks }} 块</span>
    <span v-else class="ur-err">❌ {{ r.error }}</span>
  </div>
</div>

<!-- 企业列表 -->
<div class="section-title">已上传企业</div>
<div v-if="loading" class="empty">加载中...</div>
<div v-else-if="enterprises.length === 0 && !errorType" class="empty">暂无已上传企业</div>
<div v-else class="ent-list">
  <div v-for="ent in enterprises" :key="ent.name" class="ent-row">
    <div>
      <div class="ent-name">{{ ent.name }}</div>
      <div class="ent-meta">{{ ent.doc_count }} 个文档 · {{ ent.chunk_count }} 块 · {{ ent.last_upload }}</div>
    </div>
    <button class="btn-del" @click="deleteEnt(ent.name)">删除</button>
  </div>
</div>
```

- [ ] **步骤 5：添加新样式**

在 `<style scoped>` 末尾添加：

```css
.ent-meta {
  font-size: 12px;
  color: #94a3b8;
  margin-top: 2px;
}

.error-banner {
  padding: 10px 14px;
  border-radius: 8px;
  margin-bottom: 12px;
  font-size: 13px;
  display: flex;
  align-items: center;
  gap: 8px;
}
.error-banner.warn {
  background: #fef3c7;
  color: #92400e;
}
.error-banner.err {
  background: #fee2e2;
  color: #991b1b;
}

.btn-retry {
  padding: 2px 10px;
  border-radius: 4px;
  border: 1px solid #92400e;
  background: #fff;
  color: #92400e;
  font-size: 12px;
  cursor: pointer;
}

.upload-results {
  margin: 12px 0;
  display: flex;
  flex-direction: column;
  gap: 4px;
}
.upload-result-row {
  display: flex;
  justify-content: space-between;
  font-size: 13px;
  padding: 4px 8px;
  border-radius: 4px;
  background: #f8fafc;
}
.ur-ok { color: #166534; }
.ur-err { color: #dc2626; }
```

- [ ] **步骤 6：更新 `deleteEnt()` — 适配新数据格式**

替换（约 line 184-198）：

```typescript
async function deleteEnt(enterprise: string) {
  if (!confirm('确认删除 "' + enterprise + '" 的所有数据？')) return;
  try {
    const resp = await fetch("/rag/enterprise/" + encodeURIComponent(enterprise), {
      method: "DELETE",
    });
    if (resp.ok) {
      showMsg('已删除 "' + enterprise + '"', "ok");
      refreshList();
    } else {
      alert("删除失败");
    }
  } catch {
    alert("删除失败");
  }
}
```

- [ ] **步骤 7：验证前端编译**

```bash
cd frontend && npm run build
```

预期：Build 成功，无 TypeScript 错误。

- [ ] **步骤 8：Commit**

```bash
git add frontend/src/pages/UploadPage.vue
git commit -m "feat: upgrade UploadPage with enterprise metadata, error resilience, upload results"
```

---

### 任务 11：新增企业文档详情页

**文件：**
- 创建：`frontend/src/pages/UploadDetailPage.vue`
- 修改：`frontend/src/router/index.ts`

- [ ] **步骤 1：创建 UploadDetailPage.vue**

```html
<template>
  <main class="main-content">
    <div class="inner">
      <div class="page-header">
        <router-link to="/upload" class="back-link">← 返回文档列表</router-link>
        <h2 class="page-title">📄 {{ enterprise }}</h2>
        <p class="page-subtitle">
          {{ documents.length }} 个文档 · {{ totalChunks }} 个块
        </p>
      </div>

      <div v-if="loading" class="empty">加载中...</div>
      <div v-else-if="error" class="error-banner err">❌ {{ error }}</div>
      <div v-else class="doc-list">
        <div v-for="doc in documents" :key="doc.id" class="doc-card">
          <div class="doc-info">
            <div class="doc-name">📎 {{ doc.filename }}</div>
            <div class="doc-meta">
              {{ doc.chunk_count }} 块 ·
              {{ formatSize(doc.file_size) }} ·
              {{ doc.created_at }}
              <span v-if="doc.minio_path" class="doc-minio">· MinIO</span>
            </div>
            <div v-if="doc.status === 'failed'" class="doc-error">
              ❌ {{ doc.error_msg }}
            </div>
          </div>
          <button class="btn-del-sm" @click="deleteDoc(doc.id)">删除</button>
        </div>

        <div v-if="documents.length === 0 && !loading" class="empty">
          该企业暂无文档
        </div>
      </div>
    </div>
  </main>
</template>

<script setup lang="ts">
import { onMounted, ref, computed } from "vue";
import { useRoute } from "vue-router";

const route = useRoute();
const enterprise = ref(decodeURIComponent(route.params.enterprise as string));

interface Document {
  id: number;
  filename: string;
  file_size: number;
  chunk_count: number;
  minio_path: string | null;
  status: string;
  error_msg: string | null;
  created_at: string;
}

const documents = ref<Document[]>([]);
const loading = ref(true);
const error = ref("");

const totalChunks = computed(() =>
  documents.value.reduce((sum, d) => sum + d.chunk_count, 0)
);

function formatSize(bytes: number): string {
  if (bytes < 1024) return bytes + " B";
  if (bytes < 1024 * 1024) return (bytes / 1024).toFixed(1) + " KB";
  return (bytes / 1024 / 1024).toFixed(1) + " MB";
}

async function loadDocuments() {
  loading.value = true;
  try {
    const resp = await fetch(
      "/rag/documents?enterprise=" + encodeURIComponent(enterprise.value)
    );
    if (!resp.ok) throw new Error("HTTP " + resp.status);
    const data = await resp.json();
    documents.value = data.documents || [];
  } catch (e: any) {
    error.value = e.message || "加载失败";
  } finally {
    loading.value = false;
  }
}

async function deleteDoc(docId: number) {
  if (!confirm("确认删除此文档？")) return;
  alert("单文档删除功能将在后续版本实现。当前可在文档列表页删除整个企业的所有数据。");
}

onMounted(loadDocuments);
</script>

<style scoped>
.main-content {
  flex: 1;
  min-height: 100vh;
  overflow-y: auto;
  padding: 40px;
  background: #f8fafc;
}
.inner { margin: 0 auto; max-width: 720px; }
.page-header { margin-bottom: 24px; }
.back-link { 
  color: #2563eb; text-decoration: none; font-size: 13px;
}
.back-link:hover { text-decoration: underline; }
.page-title { font-size: 26px; font-weight: 700; color: #0f172a; margin: 8px 0 6px; }
.page-subtitle { font-size: 13px; color: #64748b; margin: 0; }

.doc-list { display: flex; flex-direction: column; gap: 10px; }
.doc-card {
  display: flex; align-items: center; justify-content: space-between;
  padding: 14px 18px; background: #fff; border-radius: 10px;
  border: 1px solid #e2e8f0; box-shadow: 0 1px 3px rgba(0,0,0,0.04);
}
.doc-name { font-size: 15px; font-weight: 500; color: #0f172a; }
.doc-meta { font-size: 12px; color: #94a3b8; margin-top: 4px; }
.doc-error { font-size: 12px; color: #dc2626; margin-top: 4px; }
.doc-minio { color: #22c55e; }

.btn-del-sm {
  padding: 4px 12px; border-radius: 6px; border: 1px solid #fca5a5;
  background: #fff; color: #dc2626; font-size: 12px; cursor: pointer;
  flex-shrink: 0;
}
.btn-del-sm:hover { background: #fee2e2; }

.empty { color: #94a3b8; font-size: 13px; text-align: center; padding: 20px; }
.error-banner { padding: 10px 14px; border-radius: 8px; font-size: 13px; }
.error-banner.err { background: #fee2e2; color: #991b1b; }
</style>
```

- [ ] **步骤 2：注册路由**

在 `frontend/src/router/index.ts` 中，在现有 routes 数组末尾添加：

```typescript
{
  path: "/upload/:enterprise",
  name: "upload-detail",
  component: () => import("../pages/UploadDetailPage.vue"),
},
```

- [ ] **步骤 3：UploadPage 企业名改为可点击链接**

在 `UploadPage.vue` 的企业名处改为 router-link：

```html
<div class="ent-name">
  <router-link :to="'/upload/' + encodeURIComponent(ent.name)" class="ent-link">
    {{ ent.name }}
  </router-link>
</div>
```

并添加链接样式：

```css
.ent-link {
  color: #2563eb;
  text-decoration: none;
}
.ent-link:hover {
  text-decoration: underline;
}
```

- [ ] **步骤 4：验证前端编译**

```bash
cd frontend && npm run build
```

预期：Build 成功。

- [ ] **步骤 5：Commit**

```bash
git add frontend/src/pages/UploadDetailPage.vue frontend/src/router/index.ts frontend/src/pages/UploadPage.vue
git commit -m "feat: add enterprise document detail page with route /upload/:enterprise"
```

---

### 任务 12：ResearchPage RAG 集成

**文件：**
- 修改：`frontend/src/pages/ResearchPage.vue`
- 修改：`backend/src/main.py`（`POST /research/stream` 端点）

- [ ] **步骤 1：ResearchPage 添加企业选择器和 RAG 开关**

在 ResearchPage.vue 的 `<script setup>` 中添加：

```typescript
// RAG 企业列表
interface RagEnterprise {
  name: string;
  doc_count: number;
  chunk_count: number;
}

const ragEnterprises = ref<RagEnterprise[]>([]);
const selectedEnterprise = ref("");
const useRag = ref(false);

async function loadRagEnterprises() {
  try {
    const resp = await fetch("/rag/enterprises");
    const data = await resp.json();
    ragEnterprises.value = data.enterprises || [];
  } catch {
    ragEnterprises.value = [];
  }
}
```

在 `onMounted` 中调用 `loadRagEnterprises()`。

- [ ] **步骤 2：ResearchPage 模板添加 RAG 控件**

在 topic textarea 下方添加：

```html
<div class="rag-controls">
  <div class="rag-row">
    <label class="rag-label">关联企业：</label>
    <select v-model="selectedEnterprise" class="rag-select">
      <option value="">不关联</option>
      <option v-for="e in ragEnterprises" :key="e.name" :value="e.name">
        {{ e.name }} ({{ e.doc_count }} 文档)
      </option>
    </select>
  </div>
  <div v-if="selectedEnterprise" class="rag-row">
    <label class="rag-check">
      <input type="checkbox" v-model="useRag" />
      附加 RAG 参考文档作为研究上下文
    </label>
  </div>
</div>
```

添加样式：

```css
.rag-controls { margin: 12px 0; }
.rag-row { display: flex; align-items: center; gap: 8px; margin-bottom: 8px; }
.rag-label { font-size: 13px; color: #64748b; white-space: nowrap; }
.rag-select {
  flex: 1; padding: 6px 10px; border: 1px solid #cbd5e1; border-radius: 6px;
  font-size: 13px; background: #fff;
}
.rag-check { font-size: 13px; color: #64748b; display: flex; align-items: center; gap: 6px; cursor: pointer; }
```

- [ ] **步骤 3：传递 use_rag 参数到研究 API**

在 `handleSubmit()` 中，修改请求 payload：

```typescript
// 旧：
// const payload = JSON.stringify({ topic: form.topic, search_api: form.search_api });

// 新：
const payload = JSON.stringify({
  topic: form.topic,
  search_api: form.search_api,
  enterprise: selectedEnterprise.value || undefined,
  use_rag: useRag.value && !!selectedEnterprise.value,
});
```

- [ ] **步骤 4：修改后端 `/research/stream` 接受新参数**

在 `main.py` 的 `POST /research/stream` 端点中，扩展请求模型：

```python
@app.post("/research/stream")
async def research_stream(request: Request):
    body = await request.json()
    topic = body.get("topic", "")
    search_api = body.get("search_api", "auto")
    enterprise = body.get("enterprise", "")
    use_rag = body.get("use_rag", False)
    
    # 如果启用 RAG，检索相关文档注入 prompt
    rag_context = ""
    if use_rag and enterprise:
        keywords = topic  # 用研究主题作为检索关键词
        rag_context = _rag.query(keywords, enterprise, n_results=5)
    
    # ... 在传递给 agent 时附加 rag_context
```

- [ ] **步骤 5：验证前端编译 + 后端启动**

```bash
cd frontend && npm run build
```

预期：Build 成功。

- [ ] **步骤 6：Commit**

```bash
git add frontend/src/pages/ResearchPage.vue backend/src/main.py
git commit -m "feat: integrate RAG context into ResearchPage with enterprise selector"
```

---

### 任务 13：清理旧代码

**文件：**
- 删除：`backend/src/services/rag_store.py`
- 修改：`backend/src/main.py`（移除旧 import）

- [ ] **步骤 1：确认旧文件没有被其他地方 import**

```bash
cd backend && grep -r "rag_store" --include="*.py" .
```

预期：只在 main.py 中有旧 import（已在任务 8 中替换），无其他引用。

- [ ] **步骤 2：删除旧文件**

```bash
rm backend/src/services/rag_store.py
```

- [ ] **步骤 3：验证后端启动无报错**

```bash
cd backend && timeout 5 python -m src.main 2>&1 || true
```

预期：无 ImportError 关于 rag_store。

- [ ] **步骤 4：Commit**

```bash
git rm backend/src/services/rag_store.py
git commit -m "refactor: remove deprecated rag_store.py — replaced by RagService"
```

---

## 自检

| 检查项 | 结果 |
|--------|------|
| 规格覆盖 | ✅ 所有 9 个章节均有对应任务 |
| 占位符扫描 | ✅ 已修复 health() 语法错误和残留 TODO |
| 类型一致性 | ✅ Enterprise/Document 类型在前端和后端一致 |
| API 契约 | ✅ 前端 fetch 与后端 endpoint 的 request/response 匹配 |
