"""Ask the investigation agent one question and print the answer, its citations and the searches it made.

Usage (from the repository root; needs QDRANT_URL, QDRANT_API_KEY and GEMINI_API_KEY in .env):
    .venv/bin/python eval/ask.py "What government position was held by the woman who portrayed Corliss Archer?"
"""
import argparse
import sys
import time
from pathlib import Path

REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPOSITORY_ROOT / "backend"))  # lets this script import the casefile package

from casefile.config import get_settings  # noqa: E402
from casefile.rag.setup import build_agent  # noqa: E402

TEXT_PREVIEW_CHARACTERS = 160


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("question")
    parser.add_argument("--mode", default="hybrid_rerank", choices=["dense", "hybrid", "hybrid_rerank"])
    arguments = parser.parse_args()

    agent = build_agent(get_settings(), search_mode=arguments.mode)
    started = time.perf_counter()
    answer = agent.answer(arguments.question)
    seconds = time.perf_counter() - started

    def describe_citations(citations: list[str]) -> str:
        return ", ".join(answer.source_titles.get(chunk_id, chunk_id) for chunk_id in citations)

    print(f"\nQuestion: {answer.question}")
    if answer.should_abstain:
        print(f"ABSTAINED: {answer.abstain_reason}")
    else:
        print(f"Answer:   {answer.answer}")
    for number, claim in enumerate(answer.claims, start=1):
        print(f"  claim {number}: {claim.text}  [source: {describe_citations(claim.citations)}]")
    for conflict in answer.conflicts:
        print(f"  CONFLICT: {conflict.description}  [sources: {describe_citations(conflict.citations)}]")
    print(f"Searches ({len(answer.search_queries)}): " + " | ".join(answer.search_queries))
    print(f"LLM calls: {answer.llm_calls}, chunks retrieved: {len(answer.retrieved_chunk_ids)}, time: {seconds:.1f}s")
    for note in answer.notes:
        print(f"  note: {note[:TEXT_PREVIEW_CHARACTERS]}")


if __name__ == "__main__":
    main()
