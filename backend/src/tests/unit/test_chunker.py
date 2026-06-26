"""chunker 单元测试"""
import pytest
from services.chunker import Chunker


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
        assert len(chunks) == 2

    def test_chunk_paragraph_empty(self):
        c = Chunker()
        chunks = c.chunk("")
        assert chunks == []

    def test_chunk_paragraph_merge_short(self):
        c = Chunker(chunk_size=500)
        text = "短句A。\n\n短句B。\n\n短句C。"
        chunks = c.chunk(text)
        assert len(chunks) == 1

    def test_chunk_unknown_strategy_raises(self):
        c = Chunker(strategy="unknown")
        with pytest.raises(ValueError, match="Unknown strategy"):
            c.chunk("test")
