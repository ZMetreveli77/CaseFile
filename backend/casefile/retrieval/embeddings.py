"""Text -> dense vector (meaning). The real model runs locally via fastembed; tests use a fake."""
from typing import Protocol

EMBEDDING_BATCH_SIZE = 64


class TextEmbedder(Protocol):
    dimension: int

    def embed_documents(self, texts: list[str]) -> list[list[float]]: ...
    def embed_query(self, text: str) -> list[float]: ...


class FastEmbedEmbedder:
    """bge-small-en-v1.5: 384-dim, small enough for a free 512 MB server."""

    def __init__(self, model_name: str = "BAAI/bge-small-en-v1.5", dimension: int = 384):
        self.model_name = model_name
        self.dimension = dimension
        self.model = None  # loaded on first use, so importing this module stays fast

    def load_model(self):
        if self.model is None:
            from fastembed import TextEmbedding
            self.model = TextEmbedding(self.model_name)
        return self.model

    def embed_documents(self, texts: list[str]) -> list[list[float]]:
        vectors = self.load_model().embed(texts, batch_size=EMBEDDING_BATCH_SIZE)
        return [vector.tolist() for vector in vectors]

    def embed_query(self, text: str) -> list[float]:
        # bge models were trained with this prefix on queries; it improves retrieval.
        [vector] = self.load_model().query_embed([text])
        return vector.tolist()
