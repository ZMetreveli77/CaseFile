import pytest

from casefile.models import Chunk, Document


class InMemoryStore:
    """Fake DocumentStore for tests."""

    def __init__(self):
        self.docs: dict[str, Document] = {}
        self.chunks: dict[str, list[Chunk]] = {}

    def get_document(self, doc_id):
        return self.docs.get(doc_id)

    def find_by_hash(self, content_hash):
        return next((d for d in self.docs.values() if d.content_hash == content_hash), None)

    def upsert(self, doc, chunks):
        self.docs[doc.doc_id] = doc
        self.chunks[doc.doc_id] = chunks

    def delete(self, doc_id):
        self.docs.pop(doc_id, None)
        return [c.chunk_id for c in self.chunks.pop(doc_id, [])]

    def iter_chunks(self):
        for chunks in self.chunks.values():
            yield from chunks


@pytest.fixture
def store():
    return InMemoryStore()
