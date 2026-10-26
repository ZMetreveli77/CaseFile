from dataclasses import dataclass, field
from typing import Iterable, Protocol

from casefile.ingestion.chunking import MAX_CHUNK_CHARACTERS, OVERLAP_CHARACTERS, chunk_document
from casefile.ingestion.dedup import DuplicateDetector
from casefile.ingestion.loaders import load_documents
from casefile.models import Chunk, Document

# Documents handled per round trip to the store. Each batch costs 3 calls (lookup ids, lookup hashes, upsert)
# instead of 3 calls per document, which matters when the store is a cloud service.
INGEST_BATCH_SIZE = 256


class DocumentStore(Protocol):
    """What the pipeline needs from storage. Implemented by QdrantStore; batch methods keep network calls low."""

    def get_documents(self, doc_ids: list[str]) -> dict[str, Document]: ...  # doc_id -> stored document
    def find_by_hashes(self, content_hashes: list[str]) -> dict[str, Document]: ...  # hash -> stored document
    def upsert_many(self, items: list[tuple[Document, list[Chunk]]]) -> None: ...
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
        if duplicate_detector is None:
            # Default in-memory index: rebuild it from what is already stored (slow for a large store).
            duplicate_detector = DuplicateDetector()
            for stored_chunk in store.iter_chunks():
                duplicate_detector.add(stored_chunk.chunk_id, stored_chunk.text)
        # A detector passed in (e.g. QdrantDuplicateDetector) brings its own knowledge: nothing to rebuild.
        self.duplicate_detector = duplicate_detector

    def ingest_file(self, file_name: str, file_bytes: bytes) -> list[IngestResult]:
        return self.ingest_documents(load_documents(file_name, file_bytes))

    def ingest_document(self, document: Document) -> IngestResult:
        [result] = self.ingest_documents([document])
        return result

    def ingest_documents(self, documents: list[Document], batch_size: int = INGEST_BATCH_SIZE) -> list[IngestResult]:
        """Results come back in the same order as `documents`."""
        results = []
        for batch_start in range(0, len(documents), batch_size):
            results.extend(self.ingest_batch(documents[batch_start:batch_start + batch_size]))
        return results

    def ingest_batch(self, documents: list[Document]) -> list[IngestResult]:
        # Assumes doc_ids are unique within one batch (the loaders and the corpus builder guarantee this).
        existing_by_id = self.store.get_documents([document.doc_id for document in documents])
        stored_by_hash = self.store.find_by_hashes([document.content_hash for document in documents])
        owner_by_hash_in_batch: dict[str, str] = {}  # same content twice in one batch: the store can't know yet

        results, items_to_store = [], []
        for document in documents:
            existing_document = existing_by_id.get(document.doc_id)
            is_unchanged = existing_document is not None and existing_document.content_hash == document.content_hash
            if is_unchanged:
                results.append(IngestResult(document.doc_id, document.title, "unchanged"))
                continue

            stored_owner = stored_by_hash.get(document.content_hash)
            content_owner_id = stored_owner.doc_id if stored_owner else owner_by_hash_in_batch.get(document.content_hash)
            is_duplicate = content_owner_id is not None and content_owner_id != document.doc_id
            if is_duplicate:
                results.append(IngestResult(document.doc_id, document.title, "duplicate", duplicate_of=content_owner_id))
                continue
            owner_by_hash_in_batch[document.content_hash] = document.doc_id

            status = "added"
            if existing_document is not None:
                self.delete(document.doc_id)
                status = "updated"

            unique_chunks, duplicate_chunks = self.split_into_unique_chunks(document)
            document.metadata["duplicate_chunks"] = len(duplicate_chunks)
            items_to_store.append((document, unique_chunks))
            results.append(IngestResult(document.doc_id, document.title, status,
                                        chunks=len(unique_chunks), skipped_chunks=duplicate_chunks))

        if items_to_store:
            self.store.upsert_many(items_to_store)
            # The batch is stored now, so the detector can find these chunks in the store itself.
            self.duplicate_detector.forget_recently_added()
        return results

    def split_into_unique_chunks(self, document: Document) -> tuple[list[Chunk], list[dict]]:
        unique_chunks, duplicate_chunks = [], []
        for chunk in chunk_document(document, self.strategy, self.max_characters, self.overlap_characters):
            duplicate_chunk_id = self.duplicate_detector.find_duplicate(chunk.text)
            if duplicate_chunk_id is not None:
                duplicate_chunks.append({"chunk_id": chunk.chunk_id, "duplicate_of": duplicate_chunk_id})
                continue
            self.duplicate_detector.add(chunk.chunk_id, chunk.text)
            unique_chunks.append(chunk)
        return unique_chunks, duplicate_chunks

    def delete(self, doc_id: str) -> bool:
        """Remove a document and its chunks. Returns False if it did not exist."""
        if doc_id not in self.store.get_documents([doc_id]):
            return False
        for removed_chunk_id in self.store.delete(doc_id):
            self.duplicate_detector.remove(removed_chunk_id)
        return True
