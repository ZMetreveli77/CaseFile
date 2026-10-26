"""Measure what makes the API server slow to start: the same steps as build_services, each timed separately.

Time and memory are measured in separate runs: tracemalloc makes the index build about 7x slower, so timing a run
with it on would make step 3 look far worse than it is.

Usage (from the repository root; needs QDRANT_URL and QDRANT_API_KEY in .env):
    .venv/bin/python eval/measure_startup.py            # time of each step (tracemalloc off)
    .venv/bin/python eval/measure_startup.py --memory   # memory of the duplicate index (times are NOT reliable)
"""
import argparse
import resource
import sys
import time
import tracemalloc
from pathlib import Path

REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPOSITORY_ROOT / "backend"))  # lets this script import the casefile package

from casefile.config import get_settings  # noqa: E402
from casefile.ingestion.dedup import DuplicateDetector  # noqa: E402
from casefile.rag.setup import build_store  # noqa: E402

BYTES_PER_MEGABYTE = 1024 * 1024
RENDER_MEMORY_MEGABYTES = 512  # the free Render instance the server runs on


def measure_process_peak_megabytes() -> float:
    """Peak memory of the whole process (Python + model + data). ru_maxrss is bytes on macOS, kilobytes on Linux."""
    peak = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
    return peak / BYTES_PER_MEGABYTE if sys.platform == "darwin" else peak / 1024


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--memory", action="store_true",
                        help="measure the duplicate index's memory with tracemalloc (makes step 3 ~7x slower)")
    arguments = parser.parse_args()
    should_measure_memory = arguments.memory

    settings = get_settings()
    if not settings.qdrant_url:
        sys.exit("QDRANT_URL is not set. Add QDRANT_URL and QDRANT_API_KEY to .env.")
    timings: list[tuple[str, float, str]] = []  # (step, seconds, megabytes as text)

    # Step 1: the embedding model. FastEmbedEmbedder loads lazily, so the first embed_query forces the load.
    started = time.perf_counter()
    store, embedder = build_store(settings)
    embedder.embed_query("warm up")
    timings.append(("1. load embedding model", time.perf_counter() - started, "-"))
    print(f"step 1 done, process peak so far: {measure_process_peak_megabytes():.0f} MB", flush=True)

    # Step 2: read every stored chunk from Qdrant (what IngestionPipeline.__init__ loops over).
    started = time.perf_counter()
    chunks = list(store.iter_chunks())
    timings.append(("2. read all chunks from Qdrant", time.perf_counter() - started, "-"))
    print(f"step 2 done: {len(chunks):,} chunks", flush=True)

    # Step 3: build the MinHash/LSH duplicate index. In --memory mode tracemalloc counts only what is allocated
    # from here on, i.e. the index itself; it makes this step about 7x slower, so that run's time is not reported.
    if should_measure_memory:
        tracemalloc.start()
    started = time.perf_counter()
    duplicate_detector = DuplicateDetector()
    for chunk in chunks:
        duplicate_detector.add(chunk.chunk_id, chunk.text)
    index_seconds = time.perf_counter() - started
    index_megabytes = "-"
    if should_measure_memory:
        current_bytes, peak_bytes = tracemalloc.get_traced_memory()
        tracemalloc.stop()
        index_megabytes = f"{current_bytes / BYTES_PER_MEGABYTE:.0f} (peak {peak_bytes / BYTES_PER_MEGABYTE:.0f})"
    timings.append(("3. build duplicate index", index_seconds, index_megabytes))

    total_seconds = sum(seconds for _, seconds, _ in timings)
    mode = "MEMORY run: times are inflated by tracemalloc, use the time run for seconds" if should_measure_memory \
        else "TIME run: tracemalloc off, use --memory for MB"
    print(f"\n{mode}")
    print(f"{'step':<34} {'seconds':>8} {'%':>5}  MB")
    for step, seconds, megabytes in timings:
        print(f"{step:<34} {seconds:>8.1f} {100 * seconds / total_seconds:>4.0f}%  {megabytes}")
    print(f"{'total':<34} {total_seconds:>8.1f}")

    process_peak = measure_process_peak_megabytes()
    print(f"\nchunks indexed:          {len(chunks):,}")
    if should_measure_memory:
        print(f"index memory per chunk:  {current_bytes / max(len(chunks), 1):,.0f} bytes")
    print(f"whole process peak:      {process_peak:.0f} MB of Render's {RENDER_MEMORY_MEGABYTES} MB "
          f"({100 * process_peak / RENDER_MEMORY_MEGABYTES:.0f}%)")


if __name__ == "__main__":
    main()