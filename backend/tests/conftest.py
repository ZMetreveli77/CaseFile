import pytest

from casefile.models import Chunk, Document


class InMemoryStore:
    """Fake DocumentStore for tests."""

    def __init__(self):
        self.documents: dict[str, Document] = {}
        self.chunks_by_doc_id: dict[str, list[Chunk]] = {}

    def get_document(self, doc_id):
        return self.documents.get(doc_id)

    def find_by_hash(self, content_hash):
        return next((document for document in self.documents.values()
                     if document.content_hash == content_hash), None)

    def upsert(self, document, chunks):
        self.documents[document.doc_id] = document
        self.chunks_by_doc_id[document.doc_id] = chunks

    def delete(self, doc_id):
        self.documents.pop(doc_id, None)
        return [chunk.chunk_id for chunk in self.chunks_by_doc_id.pop(doc_id, [])]

    def iter_chunks(self):
        for chunks in self.chunks_by_doc_id.values():
            yield from chunks


@pytest.fixture
def store():
    return InMemoryStore()
