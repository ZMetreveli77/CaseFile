"""Compare the two chunking strategies (fixed-size vs sentence) on retrieval quality.

Each configuration indexes the SAME seeded sample into its own throwaway in-memory Qdrant (Qdrant Cloud is not
touched): every supporting paragraph of the evaluation questions, plus random distractor paragraphs. Then every
question with supporting paragraphs is searched and scored with the same code as eval/run_retrieval_eval.py.

At the production size (800 characters) about 85% of paragraphs fit in one chunk with either strategy, so the two
barely differ; a small size (300) is included to show what the strategies do when they really cut text.
Absolute numbers are not comparable with the full-corpus results (a smaller corpus has fewer competing paragraphs,
and different IDF statistics): only the comparison between configurations is meaningful.

Usage (from the repository root, ~15-20 min because every configuration embeds its chunks):
    .venv/bin/python eval/compare_chunking.py
"""
import json
import random
import sys
import time
from pathlib import Path

REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPOSITORY_ROOT / "backend"))  # lets this script import the casefile package
sys.path.insert(0, str(REPOSITORY_ROOT / "eval"))  # reuse the retrieval runner's scoring

from casefile.evaluation.eval_set import EVAL_SEED  # noqa: E402
from casefile.ingestion.loaders import convert_record_to_document  # noqa: E402
from casefile.ingestion.pipeline import IngestionPipeline  # noqa: E402
from casefile.retrieval.embeddings import FastEmbedEmbedder  # noqa: E402
from casefile.retrieval.search import HybridSearcher  # noqa: E402
from casefile.retrieval.store import QdrantStore, create_qdrant_client  # noqa: E402
from run_retrieval_eval import evaluate_question, summarize  # noqa: E402

DISTRACTOR_PARAGRAPHS = 5_000
SEARCH_MODE = "hybrid"  # the best mode on the dev split so far
CONFIGURATIONS = [  # (strategy, max characters, overlap characters)
    ("fixed", 800, 100),
    ("sentence", 800, 100),
    ("fixed", 300, 50),
    ("sentence", 300, 50),
]
EVAL_SET_FILE = REPOSITORY_ROOT / "eval" / "eval_set.jsonl"
CORPUS_FILE = REPOSITORY_ROOT / "data" / "corpus.jsonl"
OUTPUT_FILE = REPOSITORY_ROOT / "eval" / "results" / "chunking_comparison.json"


def read_jsonl(path: Path) -> list[dict]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def build_sample(corpus: list[dict], questions: list[dict]) -> list[dict]:
    """Every supporting paragraph + seeded random distractors, in a fixed order."""
    supporting_titles = {title for question in questions for title in question["supporting_titles"]}
    supporting = [paragraph for paragraph in corpus if paragraph["title"] in supporting_titles]
    others = [paragraph for paragraph in corpus if paragraph["title"] not in supporting_titles]
    return supporting + random.Random(EVAL_SEED).sample(others, DISTRACTOR_PARAGRAPHS)


def main() -> None:
    questions = [item for item in read_jsonl(EVAL_SET_FILE) if item["supporting_titles"]]
    sample = build_sample(read_jsonl(CORPUS_FILE), questions)
    documents = [convert_record_to_document("corpus.jsonl", number, record) for number, record in enumerate(sample)]
    embedder = FastEmbedEmbedder()
    print(f"{len(documents):,} paragraphs, {len(questions)} questions, search mode '{SEARCH_MODE}'\n", flush=True)

    report = {"paragraphs": len(documents), "search_mode": SEARCH_MODE, "configurations": []}
    for strategy, max_characters, overlap_characters in CONFIGURATIONS:
        started = time.perf_counter()
        store = QdrantStore(create_qdrant_client(), embedder)
        pipeline = IngestionPipeline(store, strategy, max_characters, overlap_characters)
        pipeline.ingest_documents(documents)
        searcher = HybridSearcher(store, embedder, mode=SEARCH_MODE)
        results = [evaluate_question(searcher, question) for question in questions]
        entry = {"strategy": strategy, "max_characters": max_characters, "overlap_characters": overlap_characters,
                 "chunks": store.count_chunks(), "seconds": round(time.perf_counter() - started),
                 "all": summarize(results),
                 "dev": summarize([result for result, question in zip(results, questions) if question["split"] == "dev"]),
                 "test": summarize([result for result, question in zip(results, questions) if question["split"] == "test"])}
        report["configurations"].append(entry)
        print(f"{strategy:>8} {max_characters:>4}: {entry['chunks']:>6,} chunks | R@5 {entry['all']['recall@5']:.3f} | "
              f"all@10 {entry['all']['all_found@10']:.3f} | MRR {entry['all']['reciprocal_rank']:.3f} | "
              f"{entry['seconds']} s", flush=True)

    OUTPUT_FILE.write_text(json.dumps(report, indent=2), encoding="utf-8")
    print(f"\nSaved {OUTPUT_FILE.relative_to(REPOSITORY_ROOT)}")


if __name__ == "__main__":
    main()
