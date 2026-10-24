"""Own reranker: query-term coverage + MMR (Maximal Marginal Relevance) for diversity.

MMR picks results one by one:  LAMBDA * relevance - (1 - LAMBDA) * max_similarity_to_already_picked
so the final list covers several documents instead of near-identical chunks from one.
"""
from casefile.models import SearchResult
from casefile.retrieval.bm25 import tokenize

COVERAGE_WEIGHT = 0.3  # share of relevance that comes from query-term coverage (rest from fused score)
MMR_LAMBDA = 0.6  # 1.0 = pure relevance, 0.0 = pure diversity; tuned in the evaluation (milestone 7)
SAME_DOCUMENT_SIMILARITY = 0.5  # minimum similarity assumed between two chunks of the same document
MIN_RELEVANCE = 0.05  # candidates below this are dropped, even if fewer than top_k remain
DETAIL_DECIMAL_PLACES = 4  # rounding for scores shown in result details (readability only)


def measure_query_coverage(query_terms: set[str], chunk_terms: set[str]) -> float:
    """Fraction of distinct query terms that appear in the chunk."""
    if not query_terms:
        return 0.0
    return len(query_terms & chunk_terms) / len(query_terms)


def measure_overlap(first_terms: set[str], second_terms: set[str]) -> float:
    """Jaccard similarity: shared terms / all terms."""
    if not first_terms or not second_terms:
        return 0.0
    return len(first_terms & second_terms) / len(first_terms | second_terms)


def rerank_results(query: str, candidates: list[SearchResult], top_k: int,
                   mmr_lambda: float = MMR_LAMBDA, min_relevance: float = MIN_RELEVANCE) -> list[SearchResult]:
    """Return new SearchResult objects (the candidates are not modified); the fused score is kept in details."""
    if not candidates:
        return []
    query_terms = set(tokenize(query))
    terms_by_chunk = {result.chunk.chunk_id: set(tokenize(result.chunk.text)) for result in candidates}
    # Min-max normalisation. RRF scores are very close together (1/61, 1/62, ...), so dividing by the max
    # would make every chunk look equally relevant and let the diversity penalty alone decide the order.
    highest_score = max(result.score for result in candidates)
    lowest_score = min(result.score for result in candidates)
    score_range = highest_score - lowest_score

    relevance_by_chunk, coverage_by_chunk = {}, {}
    for result in candidates:
        coverage = measure_query_coverage(query_terms, terms_by_chunk[result.chunk.chunk_id])
        normalized_score = (result.score - lowest_score) / score_range if score_range else 1.0
        relevance_by_chunk[result.chunk.chunk_id] = (1 - COVERAGE_WEIGHT) * normalized_score + COVERAGE_WEIGHT * coverage
        coverage_by_chunk[result.chunk.chunk_id] = coverage

    def measure_similarity(first: SearchResult, second: SearchResult) -> float:
        overlap = measure_overlap(terms_by_chunk[first.chunk.chunk_id], terms_by_chunk[second.chunk.chunk_id])
        is_same_document = first.chunk.doc_id == second.chunk.doc_id
        return max(overlap, SAME_DOCUMENT_SIMILARITY) if is_same_document else overlap

    def compute_mmr_score(result: SearchResult, already_selected: list[SearchResult]) -> float:
        redundancy = max((measure_similarity(result, picked) for picked in already_selected), default=0.0)
        return mmr_lambda * relevance_by_chunk[result.chunk.chunk_id] - (1 - mmr_lambda) * redundancy

    remaining = [result for result in candidates
                 if relevance_by_chunk[result.chunk.chunk_id] >= min_relevance]
    selected, reranked_results = [], []
    while remaining and len(selected) < top_k:
        best = max(remaining, key=lambda result: compute_mmr_score(result, selected))
        best_mmr_score = compute_mmr_score(best, selected)
        remaining.remove(best)
        selected.append(best)
        chunk_id = best.chunk.chunk_id
        reranked_results.append(SearchResult(best.chunk, round(best_mmr_score, DETAIL_DECIMAL_PLACES), {
            **best.details,
            "fused_score": best.score,
            "coverage": round(coverage_by_chunk[chunk_id], DETAIL_DECIMAL_PLACES),
            "relevance": round(relevance_by_chunk[chunk_id], DETAIL_DECIMAL_PLACES),
        }))
    return reranked_results
