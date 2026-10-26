"""Add duplicate-detection fingerprints (exact_hash, minhash, lsh_band_keys) to chunks stored before they existed.

Only the payload is updated: no re-embedding, no re-chunking. Safe to stop and re-run: only chunks that still have
no lsh_band_keys are read, so a second run continues where the first one stopped.

Usage (from the repository root):
    .venv/bin/python eval/backfill_fingerprints.py --dry-run --limit 1000   # compute only, write nothing
    .venv/bin/python eval/backfill_fingerprints.py                          # real run on Qdrant Cloud (needs .env)
"""
import argparse
import sys
import time
from pathlib import Path

REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPOSITORY_ROOT / "backend"))  # lets this script import the casefile package

from qdrant_client import QdrantClient  # noqa: E402
from qdrant_client import models as qdrant  # noqa: E402

from casefile.config import get_settings  # noqa: E402
from casefile.ingestion.dedup import compute_fingerprint  # noqa: E402
from casefile.retrieval.store import CHUNK_KEYWORD_FIELDS, create_qdrant_client  # noqa: E402

BACKFILL_BATCH_SIZE = 256  # chunks read and updated per round trip

# Chunks without lsh_band_keys, i.e. not backfilled yet. Filtering in Qdrant means done chunks are never downloaded.
MISSING_FINGERPRINT_FILTER = qdrant.Filter(
    must=[qdrant.IsEmptyCondition(is_empty=qdrant.PayloadField(key="lsh_band_keys"))])


def format_duration(seconds: float) -> str:
    minutes, seconds = divmod(int(seconds), 60)
    return f"{minutes}m{seconds:02d}s"


def build_fingerprint_update(point_id, chunk_text: str) -> qdrant.SetPayloadOperation:
    fingerprint = compute_fingerprint(chunk_text)
    payload = {"exact_hash": fingerprint.exact_hash, "minhash": fingerprint.signature,
               "lsh_band_keys": fingerprint.band_keys}  # same field names as store.build_chunk_point
    return qdrant.SetPayloadOperation(set_payload=qdrant.SetPayload(payload=payload, points=[point_id]))


def backfill_fingerprints(client: QdrantClient, chunks_collection: str, batch_size: int = BACKFILL_BATCH_SIZE,
                          limit: int | None = None, should_write: bool = True) -> int:
    """Fingerprint every chunk that has none yet (at most `limit`). Returns how many chunks were processed."""
    for field_name in CHUNK_KEYWORD_FIELDS:  # make sure the lookups the new detector makes are indexed
        client.create_payload_index(chunks_collection, field_name, qdrant.PayloadSchemaType.KEYWORD)

    remaining = client.count(chunks_collection, count_filter=MISSING_FINGERPRINT_FILTER, exact=True).count
    total = min(remaining, limit) if limit else remaining
    print(f"Chunks without a fingerprint: {remaining:,}; processing {total:,}"
          f"{' (dry run: nothing is written)' if not should_write else ''}", flush=True)

    done, next_page, started = 0, None, time.perf_counter()
    while done < total:
        points, next_page = client.scroll(chunks_collection, scroll_filter=MISSING_FINGERPRINT_FILTER,
                                          limit=min(batch_size, total - done), offset=next_page,
                                          with_payload=["text"], with_vectors=False)
        if not points:
            break
        updates = [build_fingerprint_update(point.id, point.payload["text"]) for point in points]
        if should_write:
            client.batch_update_points(chunks_collection, updates)  # one request for the whole batch
        done += len(points)
        elapsed = time.perf_counter() - started
        left = elapsed / done * (total - done)
        print(f"{done:,}/{total:,} chunks | {done / elapsed:.0f}/s | left {format_duration(left)}", flush=True)
        if next_page is None:
            break
    return done


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--batch-size", type=int, default=BACKFILL_BATCH_SIZE)
    parser.add_argument("--limit", type=int, help="only process the first N chunks (for test runs)")
    parser.add_argument("--dry-run", action="store_true", help="compute fingerprints but write nothing")
    arguments = parser.parse_args()

    settings = get_settings()
    if not settings.qdrant_url:
        sys.exit("QDRANT_URL is not set. Add QDRANT_URL and QDRANT_API_KEY to .env.")
    client = create_qdrant_client(settings.qdrant_url, settings.qdrant_api_key)

    started = time.perf_counter()
    try:
        done = backfill_fingerprints(client, settings.chunks_collection, arguments.batch_size, arguments.limit,
                                     should_write=not arguments.dry_run)
    except KeyboardInterrupt:
        print("\nStopped. Finished batches are saved; run the same command again to continue.")
        return
    print(f"Done in {format_duration(time.perf_counter() - started)}: {done:,} chunks.")
    remaining = client.count(settings.chunks_collection, count_filter=MISSING_FINGERPRINT_FILTER, exact=True).count
    print(f"Chunks still without a fingerprint: {remaining:,}")


if __name__ == "__main__":
    main()