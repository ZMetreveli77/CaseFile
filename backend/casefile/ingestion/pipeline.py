from dataclasses import dataclass, field
from typing import Iterable, Protocol

from casefile.ingestion.chunking import MAX_CHUNK_CHARACTERS, OVERLAP_CHARACTERS, chunk_document
from casefile.ingestion.dedup import DuplicateDetector
from casefile.ingestion.loaders import load_documents
from casefile.models import Chunk, Document


class DocumentStore(Protocol):
    """What the pipeline needs from storage. Implemented by the Qdrant store (milestone 3)."""

    def get_document(self, doc_id: str) -> Document | None: ...
    def find_by_hash(self, content_hash: str) -> Document | None: ...
    def upsert(self, document: Document, chunks: list[Chunk]) -> None: ...
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
    def __init__(self, store: DocumentStore, strategy: str = "sentence",
                 max_characters: int = MAX_CHUNK_CHARACTERS, overlap_characters: int = OVERLAP_CHARACTERS,
                 duplicate_detector: DuplicateDetector | None = None):
        self.store = store
        self.strategy = strategy
        self.max_characters = max_characters
        self.overlap_characters = overlap_characters
        self.duplicate_detector = duplicate_detector or DuplicateDetector()
        for stored_chunk in store.iter_chunks():  # rebuild the duplicate index from what is already stored
            self.duplicate_detector.add(stored_chunk.chunk_id, stored_chunk.text)

    def ingest_file(self, file_name: str, file_bytes: bytes) -> list[IngestResult]:
        return [self.ingest_document(document) for document in load_documents(file_name, file_bytes)]

    def ingest_document(self, document: Document) -> IngestResult:
        existing_document = self.store.get_document(document.doc_id)
        is_unchanged = existing_document is not None and existing_document.content_hash == document.content_hash
        if is_unchanged:
            return IngestResult(document.doc_id, document.title, "unchanged")

        document_with_same_content = self.store.find_by_hash(document.content_hash)
        is_duplicate = (document_with_same_content is not None and
                        document_with_same_content.doc_id != document.doc_id)
        if is_duplicate:
            return IngestResult(document.doc_id, document.title, "duplicate",
                                duplicate_of=document_with_same_content.doc_id)

        status = "added"
        if existing_document is not None:
            self.delete(document.doc_id)
            status = "updated"

        unique_chunks, duplicate_chunks = [], []
        for chunk in chunk_document(document, self.strategy, self.max_characters, self.overlap_characters):
            duplicate_chunk_id = self.duplicate_detector.find_duplicate(chunk.text)
            if duplicate_chunk_id is not None:
                duplicate_chunks.append({"chunk_id": chunk.chunk_id, "duplicate_of": duplicate_chunk_id})
                continue
            self.duplicate_detector.add(chunk.chunk_id, chunk.text)
            unique_chunks.append(chunk)

        document.metadata["duplicate_chunks"] = len(duplicate_chunks)
        self.store.upsert(document, unique_chunks)
        return IngestResult(document.doc_id, document.title, status,
                            chunks=len(unique_chunks), skipped_chunks=duplicate_chunks)

    def delete(self, doc_id: str) -> bool:
        """Remove a document and its chunks. Returns False if it did not exist."""
        if self.store.get_document(doc_id) is None:
            return False
        for removed_chunk_id in self.store.delete(doc_id):
            self.duplicate_detector.remove(removed_chunk_id)
        return True
