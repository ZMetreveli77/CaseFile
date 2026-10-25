"""Measure the average chunk length in BM25 tokens, to set AVERAGE_CHUNK_TOKENS in bm25.py.

Usage (from the repository root):
    .venv/bin/python eval/measure_chunk_tokens.py
"""
import argparse
import statistics
import sys
from pathlib import Path

REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPOSITORY_ROOT / "backend"))  # lets this script import the casefile package

from casefile.config import get_settings  # noqa: E402
from casefile.ingestion.chunking import chunk_document  # noqa: E402
from casefile.ingestion.loaders import load_documents  # noqa: E402
from casefile.retrieval.bm25 import tokenize  # noqa: E402


def measure_chunk_lengths(corpus_path: Path) -> tuple[list[int], list[int]]:
    """Return (token count, character count) for every chunk the indexing run would create."""
    settings = get_settings()
    token_counts, character_counts = [], []
    for document in load_documents(corpus_path.name, corpus_path.read_bytes()):
        chunks = chunk_document(document, settings.chunking_strategy, settings.chunk_size, settings.chunk_overlap)
        for chunk in chunks:
            token_counts.append(len(tokenize(chunk.text)))
            character_counts.append(len(chunk.text))
    return token_counts, character_counts


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--corpus", type=Path, default=REPOSITORY_ROOT / "data" / "corpus.jsonl")
    arguments = parser.parse_args()

    token_counts, character_counts = measure_chunk_lengths(arguments.corpus)
    if not token_counts:
        print("no chunks found")
        return
    print(f"chunks:           {len(token_counts):,}")
    print(f"mean tokens:      {statistics.mean(token_counts):.1f}")
    print(f"median tokens:    {statistics.median(token_counts):.1f}")
    print(f"min / max tokens: {min(token_counts)} / {max(token_counts)}")
    print(f"mean characters:  {statistics.mean(character_counts):.1f}")


if __name__ == "__main__":
    main()