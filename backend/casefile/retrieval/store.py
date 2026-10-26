"""Qdrant-backed DocumentStore: chunks with dense + BM25 sparse vectors, and a document registry."""
import uuid
from typing import Iterable

from qdrant_client import QdrantClient
from qdrant_client import models as qdrant

from casefile.ingestion.dedup import compute_fingerprint
from casefile.models import Chunk, Document, SearchResult
from casefile.retrieval import bm25
from casefile.retrieval.embeddings import TextEmbedder

DENSE_VECTOR_NAME = "dense"
SPARSE_VECTOR_NAME = "bm25"
UPLOAD_BATCH_SIZE = 128
SCROLL_PAGE_SIZE = 256
CLOUD_TIMEOUT_SECONDS = 60
# Chunk payload fields that are filtered on. Without a keyword index, every lookup scans all chunks.
# exact_hash / lsh_band_keys: duplicate lookups done by Qdrant instead of an in-memory index (see dedup.py).
CHUNK_KEYWORD_FIELDS = ("doc_id", "exact_hash", "lsh_band_keys")


def create_qdrant_client(qdrant_url: str = "", qdrant_api_key: str = "") -> QdrantClient:
    """Qdrant Cloud when a URL is configured; otherwise an in-memory instance (tests, quick local runs)."""
    if qdrant_url:
        return QdrantClient(url=qdrant_url, api_key=qdrant_api_key or None, timeout=CLOUD_TIMEOUT_SECONDS)
    return QdrantClient(":memory:")


def create_point_id(key: str) -> str:
    """Qdrant ids must be ints or UUIDs; uuid5 maps the same key to the same id every time."""
    return str(uuid.uuid5(uuid.NAMESPACE_URL, key))


def match_field(field_name: str, value: str) -> qdrant.Filter:
    return qdrant.Filter(must=[qdrant.FieldCondition(key=field_name, match=qdrant.MatchValue(value=value))])


def convert_payload_to_chunk(payload: dict) -> Chunk:
    return Chunk(chunk_id=payload["chunk_id"], doc_id=payload["doc_id"], index=payload["index"],
                 text=payload["text"], title=payload.get("title", ""), metadata=payload.get("metadata", {}))


def convert_payload_to_document(payload: dict) -> Document:
    return Document(doc_id=payload["doc_id"], title=payload["title"], text=payload.get("text", ""),
                    content_hash=payload["content_hash"], metadata=payload.get("metadata", {}))


class QdrantStore:
    def __init__(self, client: QdrantClient, embedder: TextEmbedder,
                 chunks_collection: str = "chunks", documents_collection: str = "documents"):
        self.client = client
        self.embedder = embedder
        self.chunks_collection = chunks_collection
        self.documents_collection = documents_collection
        self.create_collections_if_missing()

    def create_collections_if_missing(self) -> None:
        if not self.client.collection_exists(self.chunks_collection):
            self.client.create_collection(
                self.chunks_collection,
                vectors_config={DENSE_VECTOR_NAME: qdrant.VectorParams(size=self.embedder.dimension,
                                                                       distance=qdrant.Distance.COSINE)},
                # IDF modifier: Qdrant multiplies our BM25 term weights by corpus-wide IDF at query time.
                sparse_vectors_config={SPARSE_VECTOR_NAME: qdrant.SparseVectorParams(modifier=qdrant.Modifier.IDF)},
            )
            # Outside the "if": an existing collection (e.g. Qdrant Cloud) gets indexes added later too.
            # Creating an index that already exists is a no-op in Qdrant.
        for field_name in CHUNK_KEYWORD_FIELDS:
            self.client.create_payload_index(self.chunks_collection, field_name, qdrant.PayloadSchemaType.KEYWORD)
        if not self.client.collection_exists(self.documents_collection):
            self.client.create_collection(self.documents_collection, vectors_config={})
            for field_name in ("doc_id", "content_hash"):
                self.client.create_payload_index(self.documents_collection, field_name,
                                                 qdrant.PayloadSchemaType.KEYWORD)

    # ---- DocumentStore interface (used by IngestionPipeline; batch methods = one network call per batch) ----

    def get_documents(self, doc_ids: list[str]) -> dict[str, Document]:
        if not doc_ids:
            return {}
        points = self.client.retrieve(self.documents_collection, [create_point_id(doc_id) for doc_id in doc_ids],
                                      with_payload=True)
        documents = [convert_payload_to_document(point.payload) for point in points]
        return {document.doc_id: document for document in documents}

    def find_by_hashes(self, content_hashes: list[str]) -> dict[str, Document]:
        unique_hashes = list(dict.fromkeys(content_hashes))
        if not unique_hashes:
            return {}
        hash_filter = qdrant.Filter(must=[qdrant.FieldCondition(key="content_hash",
                                                                match=qdrant.MatchAny(any=unique_hashes))])
        document_by_hash, next_page = {}, None
        while True:
            points, next_page = self.client.scroll(self.documents_collection, scroll_filter=hash_filter,
                                                   limit=SCROLL_PAGE_SIZE, offset=next_page, with_payload=True)
            for point in points:
                document = convert_payload_to_document(point.payload)
                document_by_hash.setdefault(document.content_hash, document)
            if next_page is None:
                return document_by_hash

    def upsert_many(self, items: list[tuple[Document, list[Chunk]]]) -> None:
        all_chunks = [chunk for _, chunks in items for chunk in chunks]
        for batch_start in range(0, len(all_chunks), UPLOAD_BATCH_SIZE):
            batch = all_chunks[batch_start:batch_start + UPLOAD_BATCH_SIZE]
            dense_vectors = self.embedder.embed_documents([chunk.text for chunk in batch])
            points = [self.build_chunk_point(chunk, dense_vector) for chunk, dense_vector in zip(batch, dense_vectors)]
            self.client.upsert(self.chunks_collection, points)
        # Register documents last: if a chunk upload fails, those documents are not marked as stored,
        # so a re-run of the indexer processes them again (this is what makes indexing resumable).
        document_points = [qdrant.PointStruct(
            id=create_point_id(document.doc_id), vector={},
            payload={"doc_id": document.doc_id, "title": document.title, "text": document.text,
                     "content_hash": document.content_hash, "metadata": document.metadata,
                     "chunk_count": len(chunks)},
        ) for document, chunks in items]
        if document_points:
            self.client.upsert(self.documents_collection, document_points)

    def build_chunk_point(self, chunk: Chunk, dense_vector: list[float]) -> qdrant.PointStruct:
        sparse_vector = bm25.encode_document(chunk.text)
        fingerprint = compute_fingerprint(chunk.text)
        return qdrant.PointStruct(
            id=create_point_id(chunk.chunk_id),
            vector={DENSE_VECTOR_NAME: dense_vector,
                    SPARSE_VECTOR_NAME: qdrant.SparseVector(indices=sparse_vector.indices,
                                                            values=sparse_vector.values)},
            payload={"chunk_id": chunk.chunk_id, "doc_id": chunk.doc_id, "index": chunk.index,
                     "text": chunk.text, "title": chunk.title, "metadata": chunk.metadata,
                     # duplicate detection in Qdrant: exact copies by hash, near copies by shared LSH band key
                     "exact_hash": fingerprint.exact_hash, "minhash": fingerprint.signature,
                     "lsh_band_keys": fingerprint.band_keys},
        )

    # Single-document conveniences (used by the API and tests).

    def get_document(self, doc_id: str) -> Document | None:
        return self.get_documents([doc_id]).get(doc_id)

    def find_by_hash(self, content_hash: str) -> Document | None:
        return self.find_by_hashes([content_hash]).get(content_hash)

    def upsert(self, document: Document, chunks: list[Chunk]) -> None:
        self.upsert_many([(document, chunks)])

    def count_chunks(self) -> int:
        return self.client.count(self.chunks_collection, exact=True).count

    def delete(self, doc_id: str) -> list[str]:
        removed_chunk_ids = [chunk.chunk_id for chunk in self.iter_chunks(doc_id)]
        self.client.delete(self.chunks_collection, qdrant.FilterSelector(filter=match_field("doc_id", doc_id)))
        self.client.delete(self.documents_collection, qdrant.PointIdsList(points=[create_point_id(doc_id)]))
        return removed_chunk_ids

    def iter_chunks(self, doc_id: str | None = None) -> Iterable[Chunk]:
        scroll_filter = match_field("doc_id", doc_id) if doc_id else None
        next_page = None
        while True:
            points, next_page = self.client.scroll(self.chunks_collection, scroll_filter=scroll_filter,
                                                   limit=SCROLL_PAGE_SIZE, offset=next_page, with_payload=True)
            for point in points:
                yield convert_payload_to_chunk(point.payload)
            if next_page is None:
                break

    # ---- Used by the API and the searcher ----

    def list_documents_page(self, limit: int, cursor: str | None = None) -> tuple[list[dict], str | None]:
        """One page of documents (without their text) and the cursor for the next page (None on the last page).
        The corpus has 66k documents, so callers page through them instead of loading all at once."""
        points, next_page = self.client.scroll(self.documents_collection, limit=limit, offset=cursor,
                                               with_payload=qdrant.PayloadSelectorExclude(exclude=["text"]))
        return [point.payload for point in points], (str(next_page) if next_page is not None else None)

    def count_documents(self) -> int:
        return self.client.count(self.documents_collection, exact=True).count

    def get_chunk(self, chunk_id: str) -> Chunk | None:
        points = self.client.retrieve(self.chunks_collection, [create_point_id(chunk_id)], with_payload=True)
        return convert_payload_to_chunk(points[0].payload) if points else None

    def search_dense(self, query_vector: list[float], limit: int) -> list[SearchResult]:
        response = self.client.query_points(self.chunks_collection, query=query_vector, using=DENSE_VECTOR_NAME,
                                            limit=limit, with_payload=True)
        return [SearchResult(convert_payload_to_chunk(point.payload), point.score) for point in response.points]

    def search_sparse(self, query_vector: bm25.SparseVector, limit: int) -> list[SearchResult]:
        if not query_vector.indices:  # e.g. the query was only stop words
            return []
        response = self.client.query_points(
            self.chunks_collection, using=SPARSE_VECTOR_NAME, limit=limit, with_payload=True,
            query=qdrant.SparseVector(indices=query_vector.indices, values=query_vector.values))
        return [SearchResult(convert_payload_to_chunk(point.payload), point.score) for point in response.points]
