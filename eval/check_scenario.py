"""Index the Larkspur Payments scenario (data/scenario) in a fresh in-memory store and ask its questions.

Nothing is written to Qdrant Cloud; only the LLM is real. Usage (from the repository root; needs GEMINI_API_KEY in .env):
    .venv/bin/python eval/check_scenario.py            # all questions
    .venv/bin/python eval/check_scenario.py 3 5        # only questions 3 and 5
"""
import argparse
import sys
import time
from pathlib import Path

REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPOSITORY_ROOT / "backend"))  # lets this script import the casefile package

from casefile.config import get_settings  # noqa: E402
from casefile.ingestion.pipeline import IngestionPipeline  # noqa: E402
from casefile.rag.setup import build_agent_for_store  # noqa: E402
from casefile.retrieval.embeddings import FastEmbedEmbedder  # noqa: E402
from casefile.retrieval.store import QdrantStore, create_qdrant_client  # noqa: E402

SCENARIO_DIRECTORY = REPOSITORY_ROOT / "data" / "scenario"
QUESTIONS_FILE_NAME = "questions.md"  # explains the scenario; not part of the documents

QUESTIONS = [
    "Which system changes caused payment processing delays in March, which services were affected, "
    "and which documents confirm it?",
    "რომელმა სისტემურმა ცვლილებებმა გამოიწვია მარტში გადახდების დამუშავების შეფერხება, რომელი სერვისები დაზიანდა "
    "და რომელი დოკუმენტები ადასტურებს ამას?",
    "How long did the card payment delay on 4 March last?",
    "What caused the refund failures on 2 April?",
    "Who approved the change that caused the authorization timeouts on 11 March?",
    "Why did the settlement run on 24 March finish late?",
    "How much revenue did Larkspur Payments lose because of the March incidents?",
]


def index_scenario(settings) -> tuple[QdrantStore, FastEmbedEmbedder]:
    embedder = FastEmbedEmbedder(settings.embedding_model, settings.embedding_dim, settings.embedding_threads)
    store = QdrantStore(create_qdrant_client(), embedder)  # no URL = in memory
    pipeline = IngestionPipeline(store, settings.chunking_strategy, settings.chunk_size, settings.chunk_overlap)
    for path in sorted(SCENARIO_DIRECTORY.iterdir()):
        if path.name == QUESTIONS_FILE_NAME:
            continue
        results = pipeline.ingest_file(path.name, path.read_bytes())
        print(f"indexed {path.name}: " + ", ".join(f"{result.status} ({result.chunks} chunks)" for result in results))
    return store, embedder


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("numbers", nargs="*", type=int, help="question numbers to ask (default: all)")
    arguments = parser.parse_args()

    settings = get_settings()
    store, embedder = index_scenario(settings)
    agent = build_agent_for_store(settings, store, embedder)
    for number in arguments.numbers or range(1, len(QUESTIONS) + 1):
        started = time.perf_counter()
        answer = agent.answer(QUESTIONS[number - 1])
        seconds = time.perf_counter() - started

        def describe_citations(citations: list[str]) -> str:
            return ", ".join(answer.source_titles.get(chunk_id, chunk_id) for chunk_id in citations)

        print(f"\n[{number}] {answer.question}")
        if answer.should_abstain:
            print(f"  ABSTAINED: {answer.abstain_reason}")
        else:
            print(f"  Answer: {answer.answer}")
        for claim in answer.claims:
            print(f"  - {claim.text}  [{describe_citations(claim.citations)}]")
        for conflict in answer.conflicts:
            print(f"  CONFLICT: {conflict.description}  [{describe_citations(conflict.citations)}]")
        print(f"  searches: {' | '.join(answer.search_queries)}")
        print(f"  LLM calls: {answer.llm_calls}, time: {seconds:.1f}s")
        for note in answer.notes:
            print(f"  note: {note}")


if __name__ == "__main__":
    main()
