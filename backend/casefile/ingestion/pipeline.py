from dataclasses import dataclass, field
from typing import Iterable, Protocol

from casefile.ingestion.chunking import chunk_document
from casefile.ingestion.dedup import Deduplicator
from casefile.ingestion.loaders import load_documents
from casefile.models import Chunk, Document


class DocumentStore(Protocol):
    """What the pipeline needs from storage. Implemented by the Qdrant store (milestone 3)."""

    def get_document(self, doc_id: str) -> Document | None: ...
    def find_by_hash(self, content_hash: str) -> Document | None: ...
    def upsert(self, doc: Document, chunks: list[Chunk]) -> None: ...
    def delete(self, doc_id: str) -> list[str]: ...  # returns removed chunk ids
    def iter_chunks(self) -> Iterable[Chunk]: ...


@dataclass
class IngestResult:
    doc_id: str
    title: str
    status: str  # added | updated | unchanged | duplicate
    chunks: int = 0
    duplicate_of: str | None = None
    skipped_chunks: list[dict] = field(default_factory=list)  # [{chunk_id, duplicate_of}]


class IngestionPipeline:
    def __init__(self, store: DocumentStore, strategy: str = "sentence", size: int = 800, overlap: int = 100,
                 dedup: Deduplicator | None = None):
        self.store = store
        self.strategy, self.size, self.overlap = strategy, size, overlap
        self.dedup = dedup or Deduplicator()
        for chunk in store.iter_chunks():  # rebuild dedup index from what is already stored
            self.dedup.add(chunk.chunk_id, chunk.text)

    def ingest_file(self, filename: str, data: bytes) -> list[IngestResult]:
        return [self.ingest_document(doc) for doc in load_documents(filename, data)]

    def ingest_document(self, doc: Document) -> IngestResult:
        existing = self.store.get_document(doc.doc_id)
        if existing and existing.content_hash == doc.content_hash:
            return IngestResult(doc.doc_id, doc.title, "unchanged")

        same_content = self.store.find_by_hash(doc.content_hash)
        if same_content and same_content.doc_id != doc.doc_id:
            return IngestResult(doc.doc_id, doc.title, "duplicate", duplicate_of=same_content.doc_id)

        status = "added"
        if existing:
            self.delete(doc.doc_id)
            status = "updated"

        kept, skipped = [], []
        for chunk in chunk_document(doc, self.strategy, self.size, self.overlap):
            dup = self.dedup.find_duplicate(chunk.text)
            if dup is not None:
                skipped.append({"chunk_id": chunk.chunk_id, "duplicate_of": dup})
                continue
            self.dedup.add(chunk.chunk_id, chunk.text)
            kept.append(chunk)

        doc.metadata["duplicate_chunks"] = len(skipped)
        self.store.upsert(doc, kept)
        return IngestResult(doc.doc_id, doc.title, status, chunks=len(kept), skipped_chunks=skipped)

    def delete(self, doc_id: str) -> bool:
        """Remove a document and its chunks. Returns False if it did not exist."""
        if self.store.get_document(doc_id) is None:
            return False
        for chunk_id in self.store.delete(doc_id):
            self.dedup.remove(chunk_id)
        return True
