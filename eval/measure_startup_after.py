"""Measure startup AFTER the redesign: the real build_services, plus what moved out of startup.

Startup no longer builds a duplicate index; instead each upload asks Qdrant. So this measures three things:
  1. build_services: what the server does before it can answer /health and /ask
  2. the embedding model's first load: lazy, so it is paid by the first /ask or upload, not at startup
  3. one duplicate lookup through Qdrant: the new cost per uploaded chunk (also checks the backfill worked)

Usage (from the repository root; needs QDRANT_URL, QDRANT_API_KEY and GEMINI_API_KEY in .env):
    .venv/bin/python eval/measure_startup_after.py | tee eval/startup_after_time.txt
    .venv/bin/python eval/measure_startup_after.py --memory | tee eval/startup_after_memory.txt
"""
import argparse
import resource
import statistics
import sys
import time
import tracemalloc
from pathlib import Path

REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPOSITORY_ROOT / "backend"))  # lets this script import the casefile package

from casefile.api.services import build_services  # noqa: E402
from casefile.config import get_settings  # noqa: E402

BYTES_PER_MEGABYTE = 1024 * 1024
MILLISECONDS_PER_SECOND = 1000
RENDER_MEMORY_MEGABYTES = 512  # the free Render instance the server runs on
SAMPLE_CHUNKS = 20  # stored chunks used to time duplicate lookups
NEAR_COPY_SUFFIX = " This sentence was added to make a near copy."
BEFORE_FILES = [REPOSITORY_ROOT / "eval" / "startup_before_time.txt",
                REPOSITORY_ROOT / "eval" / "startup_before_memory.txt"]


def measure_process_peak_megabytes() -> float:
    """Peak memory of the whole process (Python + model + data). ru_maxrss is bytes on macOS, kilobytes on Linux."""
    peak = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
    return peak / BYTES_PER_MEGABYTE if sys.platform == "darwin" else peak / 1024


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--memory", action="store_true",
                        help="measure build_services' memory with tracemalloc (its time is then NOT reliable)")
    arguments = parser.parse_args()
    should_measure_memory = arguments.memory

    settings = get_settings()
    if not settings.qdrant_url:
        sys.exit("QDRANT_URL is not set. Add QDRANT_URL and QDRANT_API_KEY to .env.")
    timings: list[tuple[str, float, str]] = []  # (step, seconds, megabytes as text)

    # Step 1: exactly what the server runs at startup.
    if should_measure_memory:
        tracemalloc.start()
    started = time.perf_counter()
    services = build_services(settings)
    startup_seconds = time.perf_counter() - started
    startup_megabytes = "-"
    if should_measure_memory:
        current_bytes, peak_bytes = tracemalloc.get_traced_memory()
        tracemalloc.stop()
        startup_megabytes = f"{current_bytes / BYTES_PER_MEGABYTE:.0f} (peak {peak_bytes / BYTES_PER_MEGABYTE:.0f})"
    timings.append(("1. build_services (= startup)", startup_seconds, startup_megabytes))

    # Step 2: the model is loaded lazily, so this cost now lands on the first request instead of on startup.
    started = time.perf_counter()
    services.store.embedder.embed_query("warm up")
    timings.append(("2. first model load (1st request)", time.perf_counter() - started, "-"))

    # Step 3: duplicate lookups through Qdrant, on real stored chunks. An exact copy must be found by exact_hash,
    # a near copy by the LSH band keys; if either is not found, the backfill is probably incomplete.
    points, _ = services.store.client.scroll(services.store.chunks_collection, limit=SAMPLE_CHUNKS,
                                             with_payload=["chunk_id", "text"], with_vectors=False)
    duplicate_detector = services.pipeline.duplicate_detector
    lookup_milliseconds, exact_found, near_found = [], 0, 0
    for point in points:
        chunk_id, chunk_text = point.payload["chunk_id"], point.payload["text"]
        for candidate_text in (chunk_text, chunk_text + NEAR_COPY_SUFFIX):
            started = time.perf_counter()
            found_chunk_id = duplicate_detector.find_duplicate(candidate_text)
            lookup_milliseconds.append((time.perf_counter() - started) * MILLISECONDS_PER_SECOND)
            is_found = found_chunk_id == chunk_id
            if candidate_text == chunk_text:
                exact_found += is_found
            else:
                near_found += is_found
    timings.append(("3. duplicate lookups (total)", sum(lookup_milliseconds) / MILLISECONDS_PER_SECOND, "-"))

    mode = "MEMORY run: times are inflated by tracemalloc, use the time run for seconds" if should_measure_memory \
        else "TIME run: tracemalloc off, use --memory for MB"
    print(f"\nAFTER the redesign. {mode}")
    print(f"{'step':<36} {'seconds':>8}  MB")
    for step, seconds, megabytes in timings:
        print(f"{step:<36} {seconds:>8.2f}  {megabytes}")

    process_peak = measure_process_peak_megabytes()
    print(f"\nduplicate lookup:        median {statistics.median(lookup_milliseconds):.0f} ms, "
          f"max {max(lookup_milliseconds):.0f} ms per chunk ({len(lookup_milliseconds)} lookups)")
    print(f"exact copies found:      {exact_found}/{len(points)}")
    print(f"near copies found:       {near_found}/{len(points)}  (a few misses can be normal for very short chunks)")
    print(f"pending chunks in memory: {len(duplicate_detector.recently_added_chunks.signature_by_key)}")
    print(f"whole process peak:      {process_peak:.0f} MB of Render's {RENDER_MEMORY_MEGABYTES} MB "
          f"({100 * process_peak / RENDER_MEMORY_MEGABYTES:.0f}%)")

    for before_file in BEFORE_FILES:  # print the saved "before" numbers underneath, for a side-by-side read
        if before_file.exists():
            print(f"\n---- BEFORE ({before_file.name}) ----\n{before_file.read_text().strip()}")


if __name__ == "__main__":
    main()