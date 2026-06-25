# RAG 上传模块全量重构设计

> 日期：2025-06-25
> 状态：已批准
> 目标：根治"已上传企业消失"问题，重构 RAG 存储架构

---

## 1. 问题诊断

### 根因

当前 `rag_store.py` 存在 4 个致命缺陷，导致企业列表间歇性变空：

| # | 问题 | 位置 | 影响 |
|---|------|------|------|
| 1 | ChromaDB 初始化失败后永久静默返回 None | `_get_collection()` 失败一次，`_collection` 全局变量永久为 None，永不重试 | 服务重启后如 ChromaDB 启动慢/网络波动 → 企业永久"消失" |
| 2 | `list_enterprises()` 静默吞掉所有异常 | 任何 ChromaDB 异常都 `return []` | 前端显示"暂无已上传企业" |
| 3 | 非原子删除-插入 | `col.delete()` 成功但 `col.add()` 失败时，旧数据已删、新数据未写入 | 企业数据丢失 |
| 4 | `col.get()` 拉全量 metadata 取企业列表 | ChromaDB 承担了"企业列表数据源"职责 | 性能差、耦合紧、单点故障 |

### 架构缺陷

**ChromaDB 承担了两个职责**：存向量 + 充当企业列表的数据源。一旦 ChromaDB 出问题（初始化失败 / 连接断开 / 查询异常），企业列表就消失。

---

## 2. 整体架构

```
┌─────────────────────────────────────────────────────┐
│                     Frontend                         │
│   UploadPage  ←──  GET /rag/enterprises              │
│        │              (含 doc_count, last_upload)     │
│   POST /rag/upload/file                              │
│   DELETE /rag/enterprise/{name}                      │
└──────────────────────┬──────────────────────────────┘
                       │
┌──────────────────────▼──────────────────────────────┐
│                  RAG Service (new)                    │
│                                                      │
│  ┌─────────────────┐  ┌───────────────────────────┐ │
│  │ MySQL            │  │ ChromaDB (向量 only)       │ │
│  │                 │  │                           │ │
│  │ rag_enterprises │  │ • chunk + embed            │ │
│  │ rag_documents   │  │ • semantic query           │ │
│  │ 可靠的真相源    │  │ • 不用于 list enterprises  │ │
│  └────────┬────────┘  └───────────────────────────┘ │
│           │                                          │
│  ┌────────▼────────┐                                │
│  │ MinIO           │                                │
│  │ 原始文件存储    │                                │
│  │ 删除联动        │                                │
│  └─────────────────┘                                │
│                                                      │
│  ┌─────────────────────────────────────────────────┐ │
│  │ Embedding Engine (可切换)                        │ │
│  │ • all-MiniLM-L6-v2 (默认)                       │ │
│  │ • BGE-small-zh (中文优化，可选)                  │ │
│  └─────────────────────────────────────────────────┘ │
│                                                      │
│  ┌─────────────────────────────────────────────────┐ │
│  │ Chunking Strategy (可配置)                       │ │
│  │ • 按段落 (当前)                                  │ │
│  │ • CHUNK_SIZE=500, 可配置                         │ │
│  └─────────────────────────────────────────────────┘ │
└──────────────────────────────────────────────────────┘
```

**关键设计原则**：
- MySQL 是真相源（enterprise → docs 关系），ChromaDB 只是向量索引
- 企业列表永远从 MySQL 读，不受 ChromaDB 状态影响
- 上传是原子的：先写 ChromaDB → 再写 MySQL，任何一步失败都回滚

---

## 3. 数据库设计

### 3.1 `rag_enterprises` — 企业索引表

```sql
CREATE TABLE rag_enterprises (
    id          BIGINT AUTO_INCREMENT PRIMARY KEY,
    name        VARCHAR(255) NOT NULL UNIQUE COMMENT '企业名称',
    doc_count   INT NOT NULL DEFAULT 0 COMMENT '文档数量',
    chunk_count INT NOT NULL DEFAULT 0 COMMENT '总块数',
    created_at  DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at  DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    INDEX idx_name (name)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='RAG企业索引';
```

### 3.2 `rag_documents` — 文档明细表

```sql
CREATE TABLE rag_documents (
    id           BIGINT AUTO_INCREMENT PRIMARY KEY,
    enterprise   VARCHAR(255) NOT NULL COMMENT '企业名称',
    filename     VARCHAR(512) NOT NULL COMMENT '原始文件名',
    file_size    BIGINT NOT NULL DEFAULT 0 COMMENT '文件大小(bytes)',
    chunk_count  INT NOT NULL DEFAULT 0 COMMENT '分块数量',
    minio_path   VARCHAR(1024) DEFAULT NULL COMMENT 'MinIO对象路径',
    status       ENUM('uploading','active','failed','deleted') NOT NULL DEFAULT 'uploading',
    error_msg    TEXT DEFAULT NULL COMMENT '失败原因',
    created_at   DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at   DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    INDEX idx_enterprise (enterprise),
    INDEX idx_status (status),
    FOREIGN KEY (enterprise) REFERENCES rag_enterprises(name) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='RAG文档明细';
```

**设计要点**：

| 决策 | 理由 |
|------|------|
| `rag_enterprises.name` UNIQUE | 企业名是业务主键 |
| FK CASCADE | 删企业自动清文档记录 |
| `status` 含 `uploading` | 支持原子上传流程 |
| `minio_path` 可空 | MinIO 失败不阻塞向量嵌入 |
| 索引 `enterprise` + `status` | 覆盖列表查询和状态过滤 |

**与 `enterprises.yaml` 的关系**：
- `enterprises.yaml` 管理贷款项目中的企业（含角色、行业、贷款金额等业务字段）
- `rag_enterprises` 管理上传过参考文档的企业（RAG 维度）
- 两者独立但有交集

---

## 4. ChromaDB 设计

### 4.1 角色边界

| 职责 | ChromaDB |
|------|:---:|
| 文本分块 + 向量嵌入 | ✅ |
| 语义检索 | ✅ |
| 按企业/文档过滤检索 | ✅ |
| 列出所有企业 | ❌ → MySQL |
| 企业-文档关系 | ❌ → MySQL |

### 4.2 Metadata 精简

```python
metadata = {
    "enterprise": "企业名",    # where 过滤
    "doc_id": 123,            # 关联 rag_documents.id，精确删除
    "chunk_idx": 0,           # 块序号
}
# 移除: "source" — 改为通过 doc_id 反查 MySQL
```

### 4.3 嵌入模型可切换

```python
MODELS = {
    "minilm":    ("all-MiniLM-L6-v2", 384),   # 英文优化，当前默认
    "bge-small": ("BGE-small-zh",      512),   # 中文优化，推荐
    "bge-large": ("BGE-large-zh",     1024),   # 中文高精度
}
```

切换模型需重建 collection（维度不同），通过 `POST /rag/admin/reindex` 触发。

### 4.4 分块策略

- 默认策略：按段落（`\n\n` 断）
- `CHUNK_SIZE = 500`（从 300 上调，中文段落通常更长）
- 预留策略接口：`semantic`（语义断点）、`sliding`（滑动窗口 overlap 50%）

---

## 5. API 设计

### 5.1 上传文件（改造）

```
POST /rag/upload/file
Content-Type: multipart/form-data

Fields:
  enterprise: string   # 企业名称
  file: binary         # 文档文件 (.md/.docx/.pdf/.html/.htm/.txt)
```

**Response**：

```json
{
  "status": "ok",
  "enterprise": "成都瑜璟物业服务有限公司",
  "filename": "票据数据.docx",
  "doc_id": 42,
  "chunks": 17,
  "minio_path": "成都瑜璟物业服务有限公司/票据数据.docx",
  "duplicate": false
}
```

**内部流程（原子化）**：

```
1. INSERT INTO rag_enterprises ... ON DUPLICATE KEY UPDATE (幂等确保企业记录存在)
2. INSERT INTO rag_documents (enterprise, filename, file_size, status='uploading')
3. 提取文本 → 分块 → 嵌入
4. ChromaDB col.add(chunks, metadata={enterprise, doc_id, chunk_idx})
5. MinIO upload (best-effort，失败不阻塞)
6. UPDATE rag_documents SET status='active', chunk_count=N, minio_path=...
7. UPDATE rag_enterprises SET doc_count=doc_count+1, chunk_count=chunk_count+N
   ↓ 任何步骤失败
8. ChromaDB col.delete(where={"doc_id": doc_id})
9. UPDATE rag_documents SET status='failed', error_msg='...'
```

### 5.2 企业列表（改造）

```
GET /rag/enterprises
```

**Response**（从 MySQL 读，不碰 ChromaDB）：

```json
{
  "enterprises": [
    {
      "name": "成都瑜璟物业服务有限公司",
      "doc_count": 3,
      "chunk_count": 51,
      "last_upload": "2025-06-24T17:29:25"
    }
  ]
}
```

### 5.3 删除企业（改造）

```
DELETE /rag/enterprise/{name}
```

**内部流程（联动删除）**：

```
1. SELECT id FROM rag_documents WHERE enterprise={name}
2. ChromaDB col.delete(where={"doc_id": {"$in": doc_ids}})
3. MinIO delete_objects(prefix="{name}/")
4. DELETE FROM rag_documents WHERE enterprise={name}   ← CASCADE
5. DELETE FROM rag_enterprises WHERE name={name}
```

### 5.4 新增接口

| 方法 | 端点 | 用途 |
|------|------|------|
| GET | `/rag/health` | ChromaDB / MySQL / Embedding / MinIO 连通状态 |
| GET | `/rag/documents?enterprise=X` | 查看某企业的文档清单 |
| POST | `/rag/admin/reindex` | 切换嵌入模型后重建全量索引 |

---

## 6. 前端改造

### 6.1 UploadPage 增强

**列表展示升级**：企业名 → 企业名 + 文档数量 + 最后上传时间

**错误状态分区**：
- 网络异常 → 黄色 banner + 显示缓存数据 + 重试按钮
- 服务异常 → 红色 banner
- 正常空列表 → "暂无已上传企业"

**异常保护**：`refreshList()` 捕获异常时保留上次成功数据，不清空 `enterprises`

**上传结果明细**：展示每个文件的成功/失败状态

### 6.2 ResearchPage RAG 集成（新增）

在 ResearchPage 新增 "附加 RAG 参考文档" 复选框：
- 勾选后，研究请求携带 `use_rag: true` + `enterprise` 参数
- 后端在 LLM prompt 中注入 `rag_query()` 返回的相关文档块

### 6.3 企业文档详情页（新增）

路由 `/loan/upload/:enterprise`：
- 展示企业下所有文档列表（文件名、块数、上传时间）
- 支持预览、重新上传、删除单个文档
- 支持上传更多文档

---

## 7. 错误处理与可观测性

### 7.1 健康探针

```
GET /rag/health

{
  "chromadb":  "ok" | "degraded" | "down",
  "mysql":     "ok" | "down",
  "embedding": "ok" | "degraded" | "down",
  "minio":     "ok" | "degraded" | "down"
}
```

### 7.2 关键防护

| 场景 | 当前 | 改造后 |
|------|------|--------|
| ChromaDB 挂了 | 列表返回 `[]` | 列表从 MySQL 正常返回 |
| 嵌入模型下载失败 | `_get_collection()` 返回 None，永不恢复 | 启动预下载 + 健康探针 + 手动 reload |
| 上传中途 ChromaDB 崩溃 | 旧数据已删、新数据未写 | status='failed' 可重试，旧数据保留 |
| MySQL 挂了 | N/A | 返回 503，前端显示"服务暂不可用" |
| 重复上传同文件 | 静默覆盖 | 弹窗确认 |

### 7.3 结构化日志

前缀规范 `rag.<component>.<action>`：
- `rag.upload.start` / `rag.upload.chunk` / `rag.upload.complete`
- `rag.chromadb.error` / `rag.mysql.error`
- 每条日志含关键上下文：enterprise、filename、doc_id、duration_ms

---

## 8. 后端模块拆分

```
backend/src/services/
  rag_service.py      # 统一入口，编排上传/列表/删除/查询
  rag_repo.py         # MySQL CRUD（rag_enterprises + rag_documents）
  chroma_store.py     # ChromaDB 操作（仅向量存/查/删）
  embedding.py        # 嵌入引擎（可切换模型）
  chunker.py          # 分块策略（可配置）
```

---

## 9. 迁移计划

| 阶段 | 内容 | 可回滚 |
|------|------|:---:|
| 0 | MySQL 建表 DDL | ❌ |
| 1 | 后端 RAG Service 重写（5 个新文件） | ✅ |
| 2 | API 改造（3 个改造 + 3 个新增） | ✅ |
| 3 | 前端改造（UploadPage + ResearchPage + 详情页） | ✅ |
| 4 | 数据迁移（ChromaDB metadata → MySQL 索引） | ✅ |
| 5 | 清理旧代码（删除 `rag_store.py`） | ✅ |
