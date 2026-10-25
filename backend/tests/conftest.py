import math
import re
import zlib

import pytest
from qdrant_client import QdrantClient

from casefile.models import Chunk, Document
from casefile.retrieval.store import QdrantStore

FAKE_EMBEDDING_DIMENSION = 384


class FakeEmbedder:
    """Bag-of-words hashed into a fixed-size vector: texts sharing words get similar vectors. No model download."""

    dimension = FAKE_EMBEDDING_DIMENSION

    def embed_text(self, text):
        vector = [0.0] * self.dimension
        for word in re.findall(r"\w+", text.lower()):
            vector[zlib.crc32(word.encode()) % self.dimension] += 1.0
        length = math.sqrt(sum(value * value for value in vector)) or 1.0
        return [value / length for value in vector]

    def embed_documents(self, texts):
        return [self.embed_text(text) for text in texts]

    def embed_query(self, text):
        return self.embed_text(text)


class InMemoryStore:
    """Fake DocumentStore for tests."""

    def __init__(self):
        self.documents: dict[str, Document] = {}
        self.chunks_by_doc_id: dict[str, list[Chunk]] = {}
        self.call_count = 0  # store calls made by the pipeline (to check batching)

    def get_documents(self, doc_ids):
        self.call_count += 1
        return {doc_id: self.documents[doc_id] for doc_id in doc_ids if doc_id in self.documents}

    def find_by_hashes(self, content_hashes):
        self.call_count += 1
        return {document.content_hash: document for document in self.documents.values()
                if document.content_hash in content_hashes}

    def upsert_many(self, items):
        self.call_count += 1
        for document, chunks in items:
            self.documents[document.doc_id] = document
            self.chunks_by_doc_id[document.doc_id] = chunks

    def get_document(self, doc_id):
        return self.documents.get(doc_id)

    def delete(self, doc_id):
        self.documents.pop(doc_id, None)
        return [chunk.chunk_id for chunk in self.chunks_by_doc_id.pop(doc_id, [])]

    def iter_chunks(self):
        for chunks in self.chunks_by_doc_id.values():
            yield from chunks


@pytest.fixture
def store():
    return InMemoryStore()


@pytest.fixture
def embedder():
    return FakeEmbedder()


@pytest.fixture
def qdrant_store(embedder):
    return QdrantStore(QdrantClient(":memory:"), embedder)
