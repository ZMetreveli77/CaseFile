"""Duplicate detection backed by Qdrant: no in-memory index to rebuild from every stored chunk at startup.

Each stored chunk carries its fingerprint (exact_hash, minhash, lsh_band_keys) in its payload, see store.py.
Same three methods as DuplicateDetector, so IngestionPipeline can use either one.
"""
from qdrant_client import models as qdrant

from casefile.ingestion.dedup import (NEAR_DUPLICATE_SIMILARITY, DuplicateDetector, compute_fingerprint,
                                      estimate_similarity)
from casefile.retrieval.store import QdrantStore

MAX_NEAR_DUPLICATE_CANDIDATES = 50  # chunks sharing a band key fetched per lookup; bounds the cost of one check


def match_any(field_name: str, values: list[str]) -> qdrant.Filter:
    return qdrant.Filter(must=[qdrant.FieldCondition(key=field_name, match=qdrant.MatchAny(any=values))])


class QdrantDuplicateDetector:
    """Finds exact and near duplicates among stored chunks (asked from Qdrant) and chunks added since startup.

    The pipeline calls add() for each chunk BEFORE the batch is uploaded, so two near-identical chunks in the same
    upload are not in Qdrant yet. A small in-memory DuplicateDetector holds those pending chunks and is checked first.
    """

    def __init__(self, store: QdrantStore, similarity_threshold: float = NEAR_DUPLICATE_SIMILARITY,
                 max_candidates: int = MAX_NEAR_DUPLICATE_CANDIDATES):
        self.client = store.client
        self.chunks_collection = store.chunks_collection
        self.similarity_threshold = similarity_threshold
        self.max_candidates = max_candidates
        self.recently_added_chunks = DuplicateDetector(similarity_threshold)  # only chunks added since startup

    def find_duplicate(self, text: str) -> str | None:
        recent_duplicate = self.recently_added_chunks.find_duplicate(text)
        if recent_duplicate is not None:
            return recent_duplicate
        fingerprint = compute_fingerprint(text)
        return self.find_exact_in_qdrant(fingerprint.exact_hash) or self.find_near_in_qdrant(fingerprint.signature,
                                                                                            fingerprint.band_keys)

    def find_exact_in_qdrant(self, exact_hash: str) -> str | None:
        points, _ = self.client.scroll(self.chunks_collection, scroll_filter=match_any("exact_hash", [exact_hash]),
                                       limit=1, with_payload=["chunk_id"])
        return points[0].payload["chunk_id"] if points else None

    def find_near_in_qdrant(self, signature: list[int], band_keys: list[str]) -> str | None:
        """LSH: chunks sharing at least one band key are candidates; keep the most similar one above the threshold."""
        points, _ = self.client.scroll(self.chunks_collection, scroll_filter=match_any("lsh_band_keys", band_keys),
                                       limit=self.max_candidates, with_payload=["chunk_id", "minhash"])
        best_chunk_id, best_similarity = None, 0.0
        for point in points:
            similarity = estimate_similarity(tuple(signature), tuple(point.payload["minhash"]))
            if similarity > best_similarity:
                best_chunk_id, best_similarity = point.payload["chunk_id"], similarity
        is_near_duplicate = best_similarity >= self.similarity_threshold
        return best_chunk_id if is_near_duplicate else None

    def add(self, key: str, text: str) -> None:
        # Qdrant gets the fingerprint when the chunk is uploaded (store.build_chunk_point); until then, keep it here.
        self.recently_added_chunks.add(key, text)

    def forget_recently_added(self) -> None:
        """Called by the pipeline right after a batch is uploaded: those chunks are in Qdrant now, so the
        in-memory copies are no longer needed. This keeps memory small however long the server runs."""
        self.recently_added_chunks = DuplicateDetector(self.similarity_threshold)

    def remove(self, key: str) -> None:
        # Deleting the chunk in Qdrant already removed its fingerprint; only the in-memory copy is left to forget.
        self.recently_added_chunks.remove(key)