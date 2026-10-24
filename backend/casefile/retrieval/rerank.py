"""Own reranker: query-term coverage + MMR (Maximal Marginal Relevance) for diversity.

MMR picks results one by one:  LAMBDA * relevance - (1 - LAMBDA) * max_similarity_to_already_picked
so the final list covers several documents instead of near-identical chunks from one.
"""
from casefile.models import SearchResult
from casefile.retrieval.bm25 import tokenize

COVERAGE_WEIGHT = 0.3  # share of relevance that comes from query-term coverage (rest from fused score)
MMR_LAMBDA = 0.6  # 1.0 = pure relevance, 0.0 = pure diversity; tuned in the evaluation (milestone 7)
SAME_DOCUMENT_SIMILARITY = 0.5  # minimum similarity assumed between two chunks of the same document
DETAIL_DECIMAL_PLACES = 4  # rounding for scores shown in result details (readability only)
DENSE_RANK_LIMIT = 10  # chunks ranked this high by semantic search are kept without query words


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
                   mmr_lambda: float = MMR_LAMBDA) -> list[SearchResult]:
    """Return up to top_k NEW SearchResult objects; the input candidates are never modified."""
    if not candidates:
        return []
    query_terms = set(tokenize(query))
    terms_by_chunk = {result.chunk.chunk_id: set(tokenize(result.chunk.text)) for result in candidates}
    # Min-max normalisation. RRF scores are very close together (1/61, 1/62, ...), so dividing by the max
    # would make every chunk look equally relevant and let the diversity penalty alone decide the order.
    highest_score = max(result.score for result in candidates)
    lowest_score = min(result.score for result in candidates)
    score_range = highest_score - lowest_score

    coverage_by_chunk = {}
    relevance_by_chunk = {}
    for result in candidates:
        coverage = measure_query_coverage(query_terms, terms_by_chunk[result.chunk.chunk_id])
        normalized_score = (result.score - lowest_score) / score_range if score_range else 1.0
        coverage_by_chunk[result.chunk.chunk_id] = coverage
        relevance_by_chunk[result.chunk.chunk_id] = ((1 - COVERAGE_WEIGHT) * normalized_score
                                                     + COVERAGE_WEIGHT * coverage)

    def is_junk(result: SearchResult) -> bool:
        """Junk = no query word in the chunk AND semantic search did not rank it highly."""
        has_query_word = coverage_by_chunk[result.chunk.chunk_id] > 0
        dense_rank = result.details.get("dense_rank")
        is_ranked_high_by_dense_search = dense_rank is not None and dense_rank <= DENSE_RANK_LIMIT
        return not has_query_word and not is_ranked_high_by_dense_search

    def measure_similarity(first: SearchResult, second: SearchResult) -> float:
        overlap = measure_overlap(terms_by_chunk[first.chunk.chunk_id], terms_by_chunk[second.chunk.chunk_id])
        is_same_document = first.chunk.doc_id == second.chunk.doc_id
        return max(overlap, SAME_DOCUMENT_SIMILARITY) if is_same_document else overlap

    def compute_mmr_score(result: SearchResult, picked_results: list[SearchResult]) -> float:
        redundancy = max((measure_similarity(result, picked) for picked in picked_results), default=0.0)
        return mmr_lambda * relevance_by_chunk[result.chunk.chunk_id] - (1 - mmr_lambda) * redundancy

    # Always keep the top candidate, so the LLM can see the best evidence and decide itself whether to abstain.
    top_candidate = max(candidates, key=lambda result: relevance_by_chunk[result.chunk.chunk_id])
    remaining = [result for result in candidates if result is top_candidate or not is_junk(result)]

    picked_results, reranked_results = [], []
    while remaining and len(picked_results) < top_k:
        best = max(remaining, key=lambda result: compute_mmr_score(result, picked_results))
        mmr_score = compute_mmr_score(best, picked_results)
        remaining.remove(best)
        picked_results.append(best)
        # Build a NEW result instead of modifying the caller's object; the fused score is kept in details.
        reranked_results.append(SearchResult(
            chunk=best.chunk,
            score=round(mmr_score, DETAIL_DECIMAL_PLACES),
            details={
                **best.details,  # copies the dict, so the original details stay untouched
                "fused_score": best.score,
                "coverage": round(coverage_by_chunk[best.chunk.chunk_id], DETAIL_DECIMAL_PLACES),
                "relevance": round(relevance_by_chunk[best.chunk.chunk_id], DETAIL_DECIMAL_PLACES),
            },
        ))
    return reranked_results
