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
