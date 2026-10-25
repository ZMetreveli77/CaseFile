"""Spot check: for a few real HotpotQA questions, does search find the paragraphs that prove the answer?

Usage (from the repository root, after eval/index_corpus.py has filled Qdrant):
    .venv/bin/python eval/spot_check.py
"""
import argparse
import json
import sys
from pathlib import Path

REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPOSITORY_ROOT / "backend"))  # lets this script import the casefile package

from casefile.config import get_settings  # noqa: E402
from casefile.retrieval.embeddings import FastEmbedEmbedder  # noqa: E402
from casefile.retrieval.search import HybridSearcher  # noqa: E402
from casefile.retrieval.store import QdrantStore, create_qdrant_client  # noqa: E402

QUESTIONS_PER_TYPE = {"bridge": 3, "comparison": 2}  # first N of each type: a fixed, reproducible choice
SEARCH_MODES = ["dense", "hybrid", "hybrid_rerank"]
TOP_K = 8
QUESTION_WIDTH = 50  # characters of the question shown in the table


def load_spot_check_questions(questions_path: Path) -> list[dict]:
    """Return the first QUESTIONS_PER_TYPE[type] questions of each type, in file order."""
    picked_questions = []
    picked_count_by_type = {question_type: 0 for question_type in QUESTIONS_PER_TYPE}
    with questions_path.open(encoding="utf-8") as questions_file:
        for line in questions_file:
            question = json.loads(line)
            question_type = question["type"]
            if picked_count_by_type.get(question_type, 0) < QUESTIONS_PER_TYPE.get(question_type, 0):
                picked_questions.append(question)
                picked_count_by_type[question_type] += 1
            if picked_count_by_type == QUESTIONS_PER_TYPE:
                break
    return picked_questions


def find_supporting_ranks(searcher: HybridSearcher, question: dict) -> dict[str, int | None]:
    """Map each supporting title to the rank (1 = best) of its first chunk in the results, or None."""
    results = searcher.search(question["question"], top_k=TOP_K)
    rank_by_title: dict[str, int] = {}
    for rank, result in enumerate(results, start=1):
        rank_by_title.setdefault(result.chunk.title, rank)  # a title can have several chunks: keep the best
    return {title: rank_by_title.get(title) for title in question["supporting_titles"]}


def shorten(text: str, width: int) -> str:
    return text if len(text) <= width else text[:width - 3] + "..."


def print_table(mode: str, questions: list[dict], ranks_by_question: list[dict[str, int | None]]) -> int:
    """Print one table for a search mode and return how many supporting titles it found."""
    print(f"\n=== mode: {mode} (top_k={TOP_K}) ===")
    print(f"{'question':<{QUESTION_WIDTH}}  {'type':<10}  {'found':<5}  supporting titles (rank)")
    found_total = 0
    for question, rank_by_title in zip(questions, ranks_by_question):
        found_count = sum(rank is not None for rank in rank_by_title.values())
        found_total += found_count
        titles_with_ranks = ", ".join(f"{title} ({rank if rank is not None else '-'})"
                                      for title, rank in rank_by_title.items())
        print(f"{shorten(question['question'], QUESTION_WIDTH):<{QUESTION_WIDTH}}  {question['type']:<10}  "
              f"{found_count}/{len(rank_by_title):<3}  {titles_with_ranks}")
    return found_total


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--questions", type=Path, default=REPOSITORY_ROOT / "data" / "questions.jsonl")
    arguments = parser.parse_args()

    settings = get_settings()
    if not settings.qdrant_url:
        sys.exit("QDRANT_URL is not set. The spot check needs the indexed corpus in Qdrant (see .env).")

    client = create_qdrant_client(settings.qdrant_url, settings.qdrant_api_key)
    embedder = FastEmbedEmbedder(settings.embedding_model, settings.embedding_dim)
    store = QdrantStore(client, embedder, settings.chunks_collection, settings.documents_collection)

    questions = load_spot_check_questions(arguments.questions)
    possible_total = sum(len(question["supporting_titles"]) for question in questions)

    found_total_by_mode = {}
    for mode in SEARCH_MODES:
        searcher = HybridSearcher(store, embedder, mode=mode)
        ranks_by_question = [find_supporting_ranks(searcher, question) for question in questions]
        found_total_by_mode[mode] = print_table(mode, questions, ranks_by_question)

    print("\n=== summary: supporting paragraphs found ===")
    for mode, found_total in found_total_by_mode.items():
        print(f"{mode:<14} {found_total}/{possible_total}")


if __name__ == "__main__":
    main()