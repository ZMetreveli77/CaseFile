"""Answer evaluation: the multi-step agent vs a one-search baseline, scored on correctness, citations and abstention.

Every LLM call (agent, baseline and judge) goes through a disk cache in eval/cache/llm, so re-running replays saved
replies for free; only requests that changed reach the API.

Usage (from the repository root; needs Qdrant Cloud and GEMINI_API_KEY):
    .venv/bin/python eval/run_answer_eval.py --split dev --limit 3      # quick try
    .venv/bin/python eval/run_answer_eval.py --split dev
    .venv/bin/python eval/run_answer_eval.py --split test --mode hybrid_rerank
"""
import argparse
import json
import sys
import time
from dataclasses import asdict
from pathlib import Path

REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPOSITORY_ROOT / "backend"))  # lets this script import the casefile package

from casefile.config import get_settings  # noqa: E402
from casefile.evaluation.answer_eval import (answer_with_single_search, judge_answer, score_answer,  # noqa: E402
                                             summarize_answers)
from casefile.rag.agent import InvestigationAgent  # noqa: E402
from casefile.rag.citations import validate_citations  # noqa: E402
from casefile.rag.llm import GeminiProvider  # noqa: E402
from casefile.rag.llm_cache import CachingLLM  # noqa: E402
from casefile.rag.setup import build_store  # noqa: E402
from casefile.rag.tools import ToolExecutor  # noqa: E402
from casefile.retrieval.search import SEARCH_MODES, HybridSearcher  # noqa: E402

EVAL_SET_FILES = [REPOSITORY_ROOT / "eval" / "eval_set.jsonl", REPOSITORY_ROOT / "eval" / "contradictory_set.jsonl"]
CACHE_FOLDER = REPOSITORY_ROOT / "eval" / "cache" / "llm"
RESULTS_FOLDER = REPOSITORY_ROOT / "eval" / "results"
CONFIGURATIONS = ("agent", "single_search")


def load_items(split: str) -> list[dict]:
    items = []
    for path in EVAL_SET_FILES:
        if path.exists():  # the contradictory set is added by task H2
            items += [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]
    return [item for item in items if split in ("all", item["split"])]


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--split", choices=["dev", "test", "all"], default="dev")
    parser.add_argument("--configs", nargs="+", choices=CONFIGURATIONS, default=list(CONFIGURATIONS))
    parser.add_argument("--mode", choices=SEARCH_MODES, default="hybrid", help="search mode for both configurations")
    parser.add_argument("--limit", type=int, help="only the first N questions (for a quick try)")
    arguments = parser.parse_args()

    settings = get_settings()
    items = load_items(arguments.split)[:arguments.limit]
    store, embedder = build_store(settings)
    searcher = HybridSearcher(store, embedder, mode=arguments.mode)
    llm = CachingLLM(GeminiProvider(settings.gemini_api_key, settings.gemini_model, settings.llm_timeout_seconds),
                     CACHE_FOLDER)
    agent = InvestigationAgent(llm, create_tool_executor=lambda: ToolExecutor(searcher, store),
                               validate_citations=validate_citations)
    print(f"{len(items)} questions ({arguments.split}), search mode '{arguments.mode}', model {settings.gemini_model}\n")

    report = {"split": arguments.split, "mode": arguments.mode, "model": settings.gemini_model, "configurations": {}}
    for configuration in arguments.configs:
        started, results = time.perf_counter(), []
        for number, item in enumerate(items, start=1):
            if configuration == "agent":
                answer = agent.answer(item["question"])
            else:
                answer = answer_with_single_search(llm, searcher, item["question"], validate_citations)
            needs_judge = item["answer"] is not None and not answer.should_abstain
            verdict = judge_answer(llm, item["question"], item["answer"], answer.answer) if needs_judge else None
            results.append({"id": item["id"], "category": item["category"], "question": item["question"],
                            "gold": item["answer"], "judge": verdict, "scores": score_answer(item, answer, verdict),
                            "answer": asdict(answer)})
            print(f"  [{configuration}] {number}/{len(items)} {item['id']}: "
                  f"{'ABSTAIN' if answer.should_abstain else answer.answer[:60]!r}", flush=True)
        report["configurations"][configuration] = {
            "summary": summarize_answers(results), "seconds": round(time.perf_counter() - started),
            "by_category": {category: summarize_answers([result for result in results if result["category"] == category])
                            for category in sorted({result["category"] for result in results})},
            "results": results}

    print(f"\nLLM calls: {llm.misses} real, {llm.hits} replayed from the cache")
    metric_names = ["answer_accuracy_judge", "exact_match", "f1", "evidence_retrieved", "citation_precision",
                    "citation_recall", "false_abstention_rate", "abstention_recall", "conflict_detection",
                    "llm_calls_per_question"]
    print(f"\n{'metric':<24}" + "".join(f"{configuration:>16}" for configuration in report["configurations"]))
    for metric in metric_names:
        values = [report["configurations"][configuration]["summary"][metric] for configuration in report["configurations"]]
        print(f"{metric:<24}" + "".join(f"{('-' if value is None else f'{value:.3f}'):>16}" for value in values))

    RESULTS_FOLDER.mkdir(exist_ok=True)
    output_file = RESULTS_FOLDER / f"answers_{arguments.split}_{arguments.mode}.json"
    output_file.write_text(json.dumps(report, indent=2, ensure_ascii=False, default=str), encoding="utf-8")
    print(f"\nPer-question details: {output_file.relative_to(REPOSITORY_ROOT)}")


if __name__ == "__main__":
    main()
