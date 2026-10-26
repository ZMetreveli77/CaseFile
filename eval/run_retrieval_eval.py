"""Retrieval evaluation (no LLM): does search put the supporting paragraphs near the top, per search mode?

For every question with supporting paragraphs, each search mode retrieves the top results for the question text.
Scores use the metric functions in casefile/evaluation/metrics.py. Results are ranked by DOCUMENT (title): a paragraph
split into several chunks counts once, at its best rank, because HotpotQA's ground truth is per paragraph.

Usage (from the repository root; needs the indexed corpus in Qdrant Cloud):
    .venv/bin/python eval/run_retrieval_eval.py --split dev
    .venv/bin/python eval/run_retrieval_eval.py --split test --modes dense hybrid_rerank
"""
import argparse
import json
import sys
import time
from pathlib import Path

REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPOSITORY_ROOT / "backend"))  # lets this script import the casefile package

from casefile.config import get_settings  # noqa: E402
from casefile.evaluation.metrics import all_found_at_k, mean, recall_at_k, reciprocal_rank  # noqa: E402  (task H1)
from casefile.rag.setup import build_store  # noqa: E402
from casefile.retrieval.search import SEARCH_MODES, HybridSearcher  # noqa: E402

EVAL_SET_FILE = REPOSITORY_ROOT / "eval" / "eval_set.jsonl"
RESULTS_FOLDER = REPOSITORY_ROOT / "eval" / "results"
K_VALUES = (1, 3, 5, 10)
RETRIEVED_DOCUMENTS = max(K_VALUES)


def rank_documents(chunk_titles: list[str]) -> list[str]:
    """Chunk titles in rank order -> document titles in rank order, each document once (at its best rank)."""
    return list(dict.fromkeys(chunk_titles))


def evaluate_question(searcher: HybridSearcher, item: dict) -> dict:
    # Fetch extra chunks, since several chunks of one document collapse into one ranked document.
    results = searcher.search(item["question"], top_k=RETRIEVED_DOCUMENTS * 2)
    ranked_titles = rank_documents([result.chunk.title for result in results])[:RETRIEVED_DOCUMENTS]
    relevant_titles = set(item["supporting_titles"])
    scores = {f"recall@{k}": recall_at_k(ranked_titles, relevant_titles, k) for k in K_VALUES}
    scores.update({f"all_found@{k}": float(all_found_at_k(ranked_titles, relevant_titles, k)) for k in K_VALUES})
    scores["reciprocal_rank"] = reciprocal_rank(ranked_titles, relevant_titles)
    supporting_ranks = {title: (ranked_titles.index(title) + 1 if title in ranked_titles else None)
                        for title in item["supporting_titles"]}
    return {"id": item["id"], "category": item["category"], "question": item["question"],
            "supporting_ranks": supporting_ranks, "retrieved_titles": ranked_titles, "scores": scores}


def summarize(question_results: list[dict]) -> dict:
    metric_names = list(question_results[0]["scores"]) if question_results else []
    return {name: round(mean([result["scores"][name] for result in question_results]), 3) for name in metric_names}


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--split", choices=["dev", "test", "all"], default="dev")
    parser.add_argument("--modes", nargs="+", choices=SEARCH_MODES, default=list(SEARCH_MODES))
    arguments = parser.parse_args()

    items = [json.loads(line) for line in EVAL_SET_FILE.read_text(encoding="utf-8").splitlines() if line.strip()]
    items = [item for item in items if item["supporting_titles"] and arguments.split in ("all", item["split"])]
    store, embedder = build_store(get_settings())
    print(f"{len(items)} questions with supporting paragraphs ({arguments.split} split)\n")

    report = {"split": arguments.split, "questions": len(items), "modes": {}}
    for mode in arguments.modes:
        searcher = HybridSearcher(store, embedder, mode=mode)
        started = time.perf_counter()
        question_results = [evaluate_question(searcher, item) for item in items]
        categories = sorted({result["category"] for result in question_results})
        report["modes"][mode] = {
            "overall": summarize(question_results),
            "by_category": {category: summarize([result for result in question_results if result["category"] == category])
                            for category in categories},
            "seconds": round(time.perf_counter() - started, 1),
            "questions": question_results,
        }

    header = ["mode"] + [f"R@{k}" for k in K_VALUES] + ["all@5", "all@10", "MRR"]
    print("  ".join(f"{column:>13}" for column in header))
    for mode, mode_report in report["modes"].items():
        overall = mode_report["overall"]
        values = [overall[f"recall@{k}"] for k in K_VALUES] + [overall["all_found@5"], overall["all_found@10"],
                                                               overall["reciprocal_rank"]]
        print("  ".join([f"{mode:>13}"] + [f"{value:>13.3f}" for value in values]))
    for mode, mode_report in report["modes"].items():
        print(f"\n{mode} by category (R@5 / all@10 / MRR):")
        for category, scores in mode_report["by_category"].items():
            print(f"  {category:<12} {scores['recall@5']:.3f} / {scores['all_found@10']:.3f} / {scores['reciprocal_rank']:.3f}")

    RESULTS_FOLDER.mkdir(exist_ok=True)
    output_file = RESULTS_FOLDER / f"retrieval_{arguments.split}.json"
    output_file.write_text(json.dumps(report, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"\nPer-question details: {output_file.relative_to(REPOSITORY_ROOT)}")


if __name__ == "__main__":
    main()
