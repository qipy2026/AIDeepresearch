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
