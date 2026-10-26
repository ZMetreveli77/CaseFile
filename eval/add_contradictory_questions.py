"""Build the contradictory questions (task H2) as eval/contradictory_set.jsonl, split 5 dev / 5 test with a fixed seed.

Reads eval/contradictions_written.jsonl (one hand-written conflicting document + question per fact). Writes its own
file instead of eval/eval_set.jsonl, because eval/build_eval_set.py rewrites that file from scratch and would drop
these questions. eval/run_answer_eval.py loads both files. Safe to re-run: the output is replaced, never appended.

Also writes eval/contradictory_documents.jsonl, the conflicting documents in the {id, title, text} format the JSONL
loader reads, ready to upload. Before writing anything, every document is checked (find_contradiction_problems);
if one fails, nothing is written and the problems are listed.

Usage (from the repository root):
    .venv/bin/python eval/add_contradictory_questions.py                      # check + write the files
    .venv/bin/python eval/add_contradictory_questions.py --upload             # ... and ingest them into Qdrant Cloud
    .venv/bin/python eval/add_contradictory_questions.py --check-retrieval    # ... and test search on the questions
--upload changes the real corpus on purpose: the assignment asks the system to handle contradictory sources.
"""
import argparse
import json
import random
import sys
from collections import Counter
from pathlib import Path

REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPOSITORY_ROOT / "backend"))  # lets this script import the casefile package

from casefile.config import get_settings  # noqa: E402
from casefile.evaluation.eval_set import (EVAL_SEED, assign_splits, build_contradictory_items,  # noqa: E402
                                          find_contradiction_problems, find_used_titles)
from casefile.ingestion.pipeline import IngestionPipeline, IngestResult  # noqa: E402
from casefile.ingestion.qdrant_dedup import QdrantDuplicateDetector  # noqa: E402
from casefile.rag.setup import build_store  # noqa: E402
from casefile.rag.tools import SEARCH_RESULTS_PER_CALL  # noqa: E402
from casefile.retrieval.search import HybridSearcher  # noqa: E402

CONFLICTING_DOCUMENTS_FILE = REPOSITORY_ROOT / "eval" / "contradictions_written.jsonl"
CONTRADICTORY_SET_FILE = REPOSITORY_ROOT / "eval" / "contradictory_set.jsonl"
UPLOAD_DOCUMENTS_FILE = REPOSITORY_ROOT / "eval" / "contradictory_documents.jsonl"
CORPUS_FILE = REPOSITORY_ROOT / "data" / "corpus.jsonl"
EVAL_SET_FILE = REPOSITORY_ROOT / "eval" / "eval_set.jsonl"
CONTRADICTORY_CATEGORY = "contradictory"
AGENT_SEARCH_MODE = "hybrid_rerank"  # the mode build_agent_for_store gives the agent's search tool


def read_jsonl(path: Path) -> list[dict]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def write_jsonl(records: list[dict], path: Path) -> None:
    path.write_text("".join(json.dumps(record, ensure_ascii=False) + "\n" for record in records), encoding="utf-8")


def build_upload_records(conflicting_documents: list[dict]) -> list[dict]:
    """{id, title, text}: the JSONL loader turns each line into a document, using "id" for the document id.
    The title doubles as the id, like in data/corpus.jsonl, so ids are readable and unique."""
    return [{"id": document["title"], "title": document["title"], "text": document["text"]}
            for document in conflicting_documents]


def upload_documents(pipeline: IngestionPipeline, upload_file: Path) -> list[IngestResult]:
    """Ingest the upload file exactly like an API upload; print every result and return them."""
    results = pipeline.ingest_file(upload_file.name, upload_file.read_bytes())
    for result in results:
        skipped = f", SKIPPED CHUNKS: {result.skipped_chunks}" if result.skipped_chunks else ""
        print(f"  {result.status:<9} chunks={result.chunks} {result.title}{skipped}")
    return results


def find_upload_failures(results: list[IngestResult], expected_count: int) -> list[str]:
    """Every document must be stored in full: status "added" (or "unchanged" on a re-run), and no skipped chunk.
    A "duplicate" status or a skipped chunk means part of a conflict never reached the corpus."""
    failures = [] if len(results) == expected_count else [f"expected {expected_count} documents, got {len(results)}"]
    for result in results:
        if result.status not in ("added", "unchanged"):
            failures.append(f"{result.title}: status {result.status!r} (duplicate of {result.duplicate_of})")
        if result.skipped_chunks:
            failures.append(f"{result.title}: {len(result.skipped_chunks)} chunk(s) skipped as near-duplicates")
    return failures


def find_missing_titles(searcher: HybridSearcher, items: list[dict], top_k: int) -> dict[str, list[str]]:
    """For each question, search like the agent's tool does and return the supporting titles NOT in the results.
    The agent can only report a conflict if one search shows it both sources."""
    missing_by_id = {}
    for item in items:
        found_titles = {result.chunk.title for result in searcher.search(item["question"], top_k=top_k)}
        missing_titles = [title for title in item["supporting_titles"] if title not in found_titles]
        print(f"  {item['id']} [{item['split']}] {'both found' if not missing_titles else f'MISSING {missing_titles}'}")
        if missing_titles:
            missing_by_id[item["id"]] = missing_titles
    return missing_by_id


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--upload", action="store_true", help="ingest the conflicting documents into Qdrant Cloud")
    parser.add_argument("--check-retrieval", action="store_true", help="check search finds both sources")
    arguments = parser.parse_args()

    conflicting_documents = read_jsonl(CONFLICTING_DOCUMENTS_FILE)
    corpus_text_by_title = {paragraph["title"]: paragraph["text"] for paragraph in read_jsonl(CORPUS_FILE)}
    # The contradictory items themselves (if they were ever merged into the eval set) list the originals on purpose.
    other_items = [item for item in read_jsonl(EVAL_SET_FILE) if item["category"] != CONTRADICTORY_CATEGORY]
    problems = find_contradiction_problems(conflicting_documents, corpus_text_by_title,
                                           used_titles=find_used_titles(other_items))
    if problems:
        sys.exit(f"Nothing written. Fix these in {CONFLICTING_DOCUMENTS_FILE.name}:\n  " + "\n  ".join(problems))

    write_jsonl(build_upload_records(conflicting_documents), UPLOAD_DOCUMENTS_FILE)
    contradictory_items = build_contradictory_items(conflicting_documents)
    # Own seeded generator: the split is the same on every run and doesn't depend on the other categories.
    assign_splits(contradictory_items, random.Random(f"{EVAL_SEED}-{CONTRADICTORY_CATEGORY}"))
    write_jsonl(contradictory_items, CONTRADICTORY_SET_FILE)

    print(f"Wrote {len(contradictory_items)} contradictory questions to "
          f"{CONTRADICTORY_SET_FILE.relative_to(REPOSITORY_ROOT)}")
    print(f"Wrote {len(conflicting_documents)} documents to upload to "
          f"{UPLOAD_DOCUMENTS_FILE.relative_to(REPOSITORY_ROOT)} (all checks passed)")
    print(f"Split: {dict(Counter(item['split'] for item in contradictory_items))}")
    for item in contradictory_items:
        print(f"  {item['id']} [{item['split']}] {item['answer']} vs {item['conflicting_answer']}: {item['question']}")
    if not (arguments.upload or arguments.check_retrieval):
        return

    settings = get_settings()
    if not settings.qdrant_url:
        sys.exit("QDRANT_URL is not set. --upload and --check-retrieval work on the real corpus in Qdrant Cloud.")
    store, embedder = build_store(settings)
    if arguments.upload:
        print(f"\nUploading {UPLOAD_DOCUMENTS_FILE.name} to Qdrant Cloud:")
        # The same wiring as build_services: duplicates are looked up in Qdrant, not in a rebuilt in-memory index.
        pipeline = IngestionPipeline(store, settings.chunking_strategy, settings.chunk_size, settings.chunk_overlap,
                                     duplicate_detector=QdrantDuplicateDetector(store))
        failures = find_upload_failures(upload_documents(pipeline, UPLOAD_DOCUMENTS_FILE), len(conflicting_documents))
        if failures:
            sys.exit("Upload problems:\n  " + "\n  ".join(failures))
        print(f"All {len(conflicting_documents)} documents stored in full. "
              f"Documents in Qdrant: {store.count_documents():,}")
    if arguments.check_retrieval:
        print(f"\nRetrieval check ({AGENT_SEARCH_MODE}, top_k={SEARCH_RESULTS_PER_CALL}, as the agent's search tool):")
        searcher = HybridSearcher(store, embedder, mode=AGENT_SEARCH_MODE)
        missing_by_id = find_missing_titles(searcher, contradictory_items, SEARCH_RESULTS_PER_CALL)
        print(f"Both sources found for {len(contradictory_items) - len(missing_by_id)}/{len(contradictory_items)} "
              "questions." + (" Fix or note the others: the agent can't report a conflict it never sees."
                              if missing_by_id else ""))


if __name__ == "__main__":
    main()