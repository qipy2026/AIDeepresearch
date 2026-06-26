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
