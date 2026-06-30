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
