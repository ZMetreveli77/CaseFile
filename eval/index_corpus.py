"""Index data/corpus.jsonl into Qdrant through the normal ingestion pipeline.

Usage (from the repository root):
    .venv/bin/python eval/index_corpus.py --in-memory --limit 2000   # quick local test, nothing is saved
    .venv/bin/python eval/index_corpus.py                            # real run into Qdrant Cloud (needs .env)

Safe to stop and re-run: documents that are already stored come back as "unchanged" and are skipped.
"""
import argparse
import sys
import time
from collections import Counter
from pathlib import Path

REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPOSITORY_ROOT / "backend"))  # lets this script import the casefile package

from casefile.config import get_settings  # noqa: E402
from casefile.ingestion.loaders import load_documents  # noqa: E402
from casefile.ingestion.pipeline import INGEST_BATCH_SIZE, IngestionPipeline  # noqa: E402
from casefile.retrieval.embeddings import FastEmbedEmbedder  # noqa: E402
from casefile.retrieval.store import QdrantStore, create_qdrant_client  # noqa: E402


def format_duration(seconds: float) -> str:
    minutes, seconds = divmod(int(seconds), 60)
    return f"{minutes}m{seconds:02d}s"


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--corpus", type=Path, default=REPOSITORY_ROOT / "data" / "corpus.jsonl")
    parser.add_argument("--batch-size", type=int, default=INGEST_BATCH_SIZE)
    parser.add_argument("--limit", type=int, help="only index the first N paragraphs (for test runs)")
    parser.add_argument("--in-memory", action="store_true", help="use a throwaway in-memory Qdrant")
    arguments = parser.parse_args()

    settings = get_settings()
    if not arguments.in_memory and not settings.qdrant_url:
        sys.exit("QDRANT_URL is not set. Add QDRANT_URL and QDRANT_API_KEY to .env, or use --in-memory.")

    documents = load_documents(arguments.corpus.name, arguments.corpus.read_bytes())
    if arguments.limit:
        documents = documents[:arguments.limit]

    client = create_qdrant_client() if arguments.in_memory else create_qdrant_client(settings.qdrant_url,
                                                                                    settings.qdrant_api_key)
    embedder = FastEmbedEmbedder(settings.embedding_model, settings.embedding_dim, settings.embedding_threads)
    store = QdrantStore(client, embedder, settings.chunks_collection, settings.documents_collection)

    started = time.perf_counter()
    pipeline = IngestionPipeline(store, settings.chunking_strategy, settings.chunk_size, settings.chunk_overlap)
    print(f"Duplicate index rebuilt from {store.count_chunks():,} stored chunks "
          f"in {format_duration(time.perf_counter() - started)}")

    status_counts: Counter = Counter()
    started = time.perf_counter()
    try:
        for batch_start in range(0, len(documents), arguments.batch_size):
            batch = documents[batch_start:batch_start + arguments.batch_size]
            status_counts.update(result.status for result in pipeline.ingest_batch(batch))
            done = batch_start + len(batch)
            elapsed = time.perf_counter() - started
            remaining = elapsed / done * (len(documents) - done)
            print(f"{done:,}/{len(documents):,} documents | {done / elapsed:.0f}/s | "
                  f"left {format_duration(remaining)} | {dict(status_counts)}", flush=True)
    except KeyboardInterrupt:
        print("\nStopped. Finished batches are stored; run the same command again to continue.")
        return

    print(f"Done in {format_duration(time.perf_counter() - started)}. {dict(status_counts)}")
    print(f"Chunks in Qdrant: {store.count_chunks():,}")


if __name__ == "__main__":
    main()
