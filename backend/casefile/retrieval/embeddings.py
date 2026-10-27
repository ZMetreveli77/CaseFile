"""Text -> dense vector (meaning). The real model runs locally via fastembed; tests use a fake."""
import threading
from typing import Protocol

# Chunks embedded at once. Memory grows with it (the model's attention tables are batch × length², and ONNX Runtime
# keeps the memory it reserved): embedding 1 MB of text took +871 MB at 64 but +70 MB at 4, only 16% slower.
# The server has 512 MB on Render, so 4 (milestone 9, H1; docs/DEPLOYMENT.md).
EMBEDDING_BATCH_SIZE = 4


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
        # One embedding at a time. The API runs requests in parallel threads that share this model; two runs at once
        # each need ONNX Runtime working memory, and two first requests would load the model twice (+151 MB each).
        # A query takes ~20 ms, so waiting is short; the slow LLM part of a question still runs in parallel.
        self.lock = threading.Lock()

    def load_model(self):
        """Call only while holding self.lock."""
        if self.model is None:
            from fastembed import TextEmbedding
            self.model = TextEmbedding(self.model_name)
        return self.model

    def embed_documents(self, texts: list[str]) -> list[list[float]]:
        vectors = []
        for batch_start in range(0, len(texts), EMBEDDING_BATCH_SIZE):
            # The lock is taken per small batch, so a question waits behind at most one batch, not a whole upload.
            with self.lock:
                batch = self.load_model().embed(texts[batch_start:batch_start + EMBEDDING_BATCH_SIZE],
                                                batch_size=EMBEDDING_BATCH_SIZE)
                vectors.extend(vector.tolist() for vector in batch)  # embed() is lazy: it runs here, inside the lock
        return vectors

    def embed_query(self, text: str) -> list[float]:
        with self.lock:
            # bge models were trained with this prefix on queries; it improves retrieval.
            [vector] = self.load_model().query_embed([text])
        return vector.tolist()
