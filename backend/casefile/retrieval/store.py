"""Qdrant-backed DocumentStore: chunks with dense + BM25 sparse vectors, and a document registry."""
import uuid
from typing import Iterable

from qdrant_client import QdrantClient
from qdrant_client import models as qdrant

from casefile.models import Chunk, Document, SearchResult
from casefile.retrieval import bm25
from casefile.retrieval.embeddings import TextEmbedder

DENSE_VECTOR_NAME = "dense"
SPARSE_VECTOR_NAME = "bm25"
UPLOAD_BATCH_SIZE = 128
SCROLL_PAGE_SIZE = 256


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
            self.client.create_payload_index(self.chunks_collection, "doc_id", qdrant.PayloadSchemaType.KEYWORD)
        if not self.client.collection_exists(self.documents_collection):
            self.client.create_collection(self.documents_collection, vectors_config={})
            for field_name in ("doc_id", "content_hash"):
                self.client.create_payload_index(self.documents_collection, field_name,
                                                 qdrant.PayloadSchemaType.KEYWORD)

    # ---- DocumentStore interface (used by IngestionPipeline) ----

    def get_document(self, doc_id: str) -> Document | None:
        points = self.client.retrieve(self.documents_collection, [create_point_id(doc_id)], with_payload=True)
        return convert_payload_to_document(points[0].payload) if points else None

    def find_by_hash(self, content_hash: str) -> Document | None:
        points, _ = self.client.scroll(self.documents_collection,
                                       scroll_filter=match_field("content_hash", content_hash),
                                       limit=1, with_payload=True)
        return convert_payload_to_document(points[0].payload) if points else None

    def upsert(self, document: Document, chunks: list[Chunk]) -> None:
        for batch_start in range(0, len(chunks), UPLOAD_BATCH_SIZE):
            batch = chunks[batch_start:batch_start + UPLOAD_BATCH_SIZE]
            dense_vectors = self.embedder.embed_documents([chunk.text for chunk in batch])
            points = []
            for chunk, dense_vector in zip(batch, dense_vectors):
                sparse_vector = bm25.encode_document(chunk.text)
                points.append(qdrant.PointStruct(
                    id=create_point_id(chunk.chunk_id),
                    vector={DENSE_VECTOR_NAME: dense_vector,
                            SPARSE_VECTOR_NAME: qdrant.SparseVector(indices=sparse_vector.indices,
                                                                    values=sparse_vector.values)},
                    payload={"chunk_id": chunk.chunk_id, "doc_id": chunk.doc_id, "index": chunk.index,
                             "text": chunk.text, "title": chunk.title, "metadata": chunk.metadata},
                ))
            self.client.upsert(self.chunks_collection, points)
        # Register the document last: if chunk upload fails, the document is not marked as stored.
        self.client.upsert(self.documents_collection, [qdrant.PointStruct(
            id=create_point_id(document.doc_id), vector={},
            payload={"doc_id": document.doc_id, "title": document.title, "text": document.text,
                     "content_hash": document.content_hash, "metadata": document.metadata,
                     "chunk_count": len(chunks)},
        )])

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

    def list_documents(self) -> list[dict]:
        documents, next_page = [], None
        while True:
            points, next_page = self.client.scroll(self.documents_collection, limit=SCROLL_PAGE_SIZE, offset=next_page,
                                                   with_payload=qdrant.PayloadSelectorExclude(exclude=["text"]))
            documents.extend(point.payload for point in points)
            if next_page is None:
                return documents

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
