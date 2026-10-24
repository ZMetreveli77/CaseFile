"""Hybrid search: dense (meaning) + BM25 (keywords) -> RRF fusion -> rerank."""
from casefile.models import SearchResult
from casefile.retrieval import bm25
from casefile.retrieval.embeddings import TextEmbedder
from casefile.retrieval.fusion import combine_search_results
from casefile.retrieval.rerank import rerank_results
from casefile.retrieval.store import QdrantStore

SEARCH_MODES = ("dense", "hybrid", "hybrid_rerank")
CANDIDATES_PER_RESULT = 4  # fetch top_k * 4 from each search so fusion/rerank have room to re-order
DEFAULT_TOP_K = 8


class HybridSearcher:
    def __init__(self, store: QdrantStore, embedder: TextEmbedder, mode: str = "hybrid_rerank",
                 dense_weight: float = 1.0, sparse_weight: float = 1.0):
        if mode not in SEARCH_MODES:
            raise ValueError(f"Unknown search mode '{mode}'. Choose one of {SEARCH_MODES}")
        self.store = store
        self.embedder = embedder
        self.mode = mode
        self.dense_weight = dense_weight
        self.sparse_weight = sparse_weight

    def search(self, query: str, top_k: int = DEFAULT_TOP_K) -> list[SearchResult]:
        if not query.strip():
            return []
        candidate_count = top_k * CANDIDATES_PER_RESULT
        dense_results = self.store.search_dense(self.embedder.embed_query(query), candidate_count)
        if self.mode == "dense":
            for rank, result in enumerate(dense_results, start=1):
                result.details["dense_rank"] = rank
            return dense_results[:top_k]

        sparse_results = self.store.search_sparse(bm25.encode_query(query), candidate_count)
        fused_results = self.fuse(dense_results, sparse_results)
        if self.mode == "hybrid":
            return fused_results[:top_k]
        return rerank_results(query, fused_results, top_k)

    def fuse(self, dense_results: list[SearchResult], sparse_results: list[SearchResult]) -> list[SearchResult]:
        result_by_chunk_id = {result.chunk.chunk_id: result for result in sparse_results + dense_results}
        dense_ids = [result.chunk.chunk_id for result in dense_results]
        sparse_ids = [result.chunk.chunk_id for result in sparse_results]
        fused_ranking = combine_search_results([dense_ids, sparse_ids], [self.dense_weight, self.sparse_weight])

        fused_results = []
        for chunk_id, fused_score in fused_ranking:
            result = result_by_chunk_id[chunk_id]
            details = {}
            if chunk_id in dense_ids:
                details["dense_rank"] = dense_ids.index(chunk_id) + 1
            if chunk_id in sparse_ids:
                details["sparse_rank"] = sparse_ids.index(chunk_id) + 1
            fused_results.append(SearchResult(result.chunk, fused_score, details))
        return fused_results
