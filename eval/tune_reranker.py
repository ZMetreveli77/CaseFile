"""Tune the reranker's three settings on the DEV split with a grid search (no LLM, no test split).

Decided BEFORE looking at any result (task T1), so the numbers can't pick the metric:
  main metric: all_found@10   multi-hop questions need BOTH supporting paragraphs, one is not enough
  tie-breaker: MRR            among equally complete rankings, prefer the one with the first hit higher

Speed: embedding the question and the two Qdrant searches don't depend on the settings, so they run ONCE per
question. Each of the 60 combinations then only re-runs rerank_results on those fused candidates (seconds, not minutes).

Usage (from the repository root; needs the indexed corpus in Qdrant Cloud):
    .venv/bin/python eval/tune_reranker.py
"""
import itertools
import json
import sys
import time
from pathlib import Path

REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPOSITORY_ROOT / "backend"))  # lets this script import the casefile package

from run_retrieval_eval import EVAL_SET_FILE, RESULTS_FOLDER, RETRIEVED_DOCUMENTS, rank_documents  # noqa: E402

from casefile.config import get_settings  # noqa: E402
from casefile.evaluation.metrics import all_found_at_k, mean, reciprocal_rank  # noqa: E402
from casefile.models import SearchResult  # noqa: E402
from casefile.rag.setup import build_store  # noqa: E402
from casefile.retrieval import bm25, rerank  # noqa: E402
from casefile.retrieval.search import CANDIDATES_PER_RESULT, HybridSearcher  # noqa: E402

TUNING_SPLIT = "dev"  # never tune on "test": its numbers must stay an honest, unseen check
COVERAGE_WEIGHTS = (0.0, 0.15, 0.3, 0.5)
MMR_LAMBDAS = (0.5, 0.6, 0.75, 0.9, 1.0)
DENSE_RANK_LIMITS = (5, 10, 20)
MAIN_METRIC_K = 10  # all_found@10
RESULT_CHUNKS = RETRIEVED_DOCUMENTS * 2  # same as run_retrieval_eval: extra chunks, since chunks collapse by document
ROWS_TO_SHOW = 10


def fetch_fused_candidates(searcher: HybridSearcher, question: str) -> list[SearchResult]:
    """The setting-independent part of HybridSearcher.search: embed, dense + sparse search, RRF fusion.
    Uses the same candidate count as search(question, top_k=RESULT_CHUNKS) would."""
    candidate_count = RESULT_CHUNKS * CANDIDATES_PER_RESULT
    dense_results = searcher.store.search_dense(searcher.embedder.embed_query(question), candidate_count)
    sparse_results = searcher.store.search_sparse(bm25.encode_query(question), candidate_count)
    return searcher.fuse(dense_results, sparse_results)


def score_ranking(chunk_titles: list[str], supporting_titles: list[str]) -> tuple[float, float]:
    """(all_found@10 as 0/1, reciprocal rank) for one question, ranked by document like run_retrieval_eval."""
    ranked_titles = rank_documents(chunk_titles)[:RETRIEVED_DOCUMENTS]
    relevant_titles = set(supporting_titles)
    return float(all_found_at_k(ranked_titles, relevant_titles, MAIN_METRIC_K)), reciprocal_rank(ranked_titles,
                                                                                              relevant_titles)


def evaluate_combination(prefetched: list[tuple[dict, list[SearchResult]]], coverage_weight: float,
                         mmr_lambda: float, dense_rank_limit: int) -> dict:
    """Rerank every question's cached candidates with these settings and average the two metrics."""
    # Read while rerank_results runs, so setting them on the module works:
    rerank.COVERAGE_WEIGHT = coverage_weight
    rerank.DENSE_RANK_LIMIT = dense_rank_limit
    all_found_scores, reciprocal_ranks = [], []
    for item, fused_candidates in prefetched:
        # MMR_LAMBDA must be PASSED: it is a default argument, filled in once when the function was defined,
        # so setting rerank.MMR_LAMBDA here would silently change nothing.
        reranked = rerank.rerank_results(item["question"], fused_candidates, RESULT_CHUNKS, mmr_lambda=mmr_lambda)
        all_found, reciprocal = score_ranking([result.chunk.title for result in reranked], item["supporting_titles"])
        all_found_scores.append(all_found)
        reciprocal_ranks.append(reciprocal)
    return {"coverage_weight": coverage_weight, "mmr_lambda": mmr_lambda, "dense_rank_limit": dense_rank_limit,
            "all_found@10": round(mean(all_found_scores), 3), "mrr": round(mean(reciprocal_ranks), 3)}


def main() -> None:
    items = [json.loads(line) for line in EVAL_SET_FILE.read_text(encoding="utf-8").splitlines() if line.strip()]
    items = [item for item in items if item["supporting_titles"] and item["split"] == TUNING_SPLIT]
    store, embedder = build_store(get_settings())
    searcher = HybridSearcher(store, embedder)

    started = time.perf_counter()
    prefetched = [(item, fetch_fused_candidates(searcher, item["question"])) for item in items]
    print(f"Fetched candidates for {len(items)} {TUNING_SPLIT} questions in {time.perf_counter() - started:.1f}s")

    original_settings = (rerank.COVERAGE_WEIGHT, rerank.DENSE_RANK_LIMIT)
    started = time.perf_counter()
    try:
        combinations = itertools.product(COVERAGE_WEIGHTS, MMR_LAMBDAS, DENSE_RANK_LIMITS)
        rows = [evaluate_combination(prefetched, *combination) for combination in combinations]
        hybrid_without_rerank = [score_ranking([result.chunk.title for result in fused[:RESULT_CHUNKS]],
                                               item["supporting_titles"]) for item, fused in prefetched]
    finally:  # restore, so the tuning can never leak into other code running in this process
        rerank.COVERAGE_WEIGHT, rerank.DENSE_RANK_LIMIT = original_settings
    print(f"Scored {len(rows)} combinations in {time.perf_counter() - started:.1f}s\n")

    # Sort by the main metric, then the tie-breaker (both higher = better). sorted() is stable, so exact ties
    # keep grid order.
    rows.sort(key=lambda row: (row["all_found@10"], row["mrr"]), reverse=True)
    current = next(row for row in rows if (row["coverage_weight"], row["mmr_lambda"], row["dense_rank_limit"])
                   == (original_settings[0], rerank.MMR_LAMBDA, original_settings[1]))
    best = rows[0]
    tied_with_best = sum((row["all_found@10"], row["mrr"]) == (best["all_found@10"], best["mrr"]) for row in rows)

    print(f"{'rank':>4}  {'coverage':>8}  {'lambda':>6}  {'dense_limit':>11}  {'all_found@10':>12}  {'MRR':>6}")
    for position, row in enumerate(rows[:ROWS_TO_SHOW], start=1):
        print(f"{position:>4}  {row['coverage_weight']:>8}  {row['mmr_lambda']:>6}  {row['dense_rank_limit']:>11}  "
              f"{row['all_found@10']:>12.3f}  {row['mrr']:>6.3f}")
    print(f"\ncurrent settings ({current['coverage_weight']}, {current['mmr_lambda']}, {current['dense_rank_limit']}): "
          f"all_found@10 {current['all_found@10']:.3f}, MRR {current['mrr']:.3f}  (rank {rows.index(current) + 1})")
    print(f"hybrid without rerank: all_found@10 {mean(score for score, _ in hybrid_without_rerank):.3f}, "
          f"MRR {mean(reciprocal for _, reciprocal in hybrid_without_rerank):.3f}")
    print(f"{tied_with_best} combination(s) tie with the best score")

    RESULTS_FOLDER.mkdir(exist_ok=True)
    output_file = RESULTS_FOLDER / f"rerank_tuning_{TUNING_SPLIT}.json"
    output_file.write_text(json.dumps({"split": TUNING_SPLIT, "questions": len(items), "main_metric": "all_found@10",
                                       "tie_breaker": "mrr", "rows": rows}, indent=2), encoding="utf-8")
    print(f"All {len(rows)} rows: {output_file.relative_to(REPOSITORY_ROOT)}")


if __name__ == "__main__":
    main()