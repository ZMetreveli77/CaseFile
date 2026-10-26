from casefile.ingestion.pipeline import IngestionPipeline
from casefile.ingestion.pipeline import IngestionPipeline
from casefile.ingestion.qdrant_dedup import QdrantDuplicateDetector
from casefile.models import Chunk, Document

INCIDENT_TEXT = ("The payment service failed on March 3rd after a configuration change to the load balancer "
                 "caused requests to time out for nearly two hours across the European region.")
NEAR_COPY = INCIDENT_TEXT.replace("nearly two hours", "nearly two hours,") + " Engineers were paged."
UNRELATED_TEXT = "Rome is the capital of Italy and has a long history of empires."


def store_chunk(qdrant_store, chunk_id, text):
    doc_id = chunk_id.split(":")[0]
    chunk = Chunk(chunk_id=chunk_id, doc_id=doc_id, index=0, text=text)
    qdrant_store.upsert(Document(doc_id=doc_id, title=doc_id, text=text, content_hash=doc_id), [chunk])


def test_finds_exact_and_near_duplicates_stored_in_qdrant(qdrant_store):
    store_chunk(qdrant_store, "inc:0", INCIDENT_TEXT)
    detector = QdrantDuplicateDetector(qdrant_store)  # a fresh detector: nothing in memory, only Qdrant knows
    assert detector.find_duplicate("  " + INCIDENT_TEXT.upper()) == "inc:0"
    assert detector.find_duplicate(NEAR_COPY) == "inc:0"
    assert detector.find_duplicate(UNRELATED_TEXT) is None


def test_finds_a_duplicate_added_in_the_same_upload_before_it_reaches_qdrant(qdrant_store):
    # The gotcha: the pipeline calls add() before the batch is uploaded, so Qdrant can't see the first chunk yet.
    detector = QdrantDuplicateDetector(qdrant_store)
    detector.add("inc:0", INCIDENT_TEXT)
    assert detector.find_duplicate(NEAR_COPY) == "inc:0"


def test_removed_chunks_are_forgotten(qdrant_store):
    detector = QdrantDuplicateDetector(qdrant_store)
    detector.add("inc:0", INCIDENT_TEXT)
    store_chunk(qdrant_store, "inc:0", INCIDENT_TEXT)
    qdrant_store.delete("inc")  # deleting in Qdrant removes the stored fingerprint
    detector.remove("inc:0")  # and remove() forgets the in-memory copy
    assert detector.find_duplicate(INCIDENT_TEXT) is None
    detector.remove("missing")  # no error


def test_pending_chunks_are_forgotten_after_upload_but_still_found_via_qdrant(qdrant_store):
    detector = QdrantDuplicateDetector(qdrant_store)
    pipeline = IngestionPipeline(qdrant_store, duplicate_detector=detector)
    [first] = pipeline.ingest_file("incident.txt", INCIDENT_TEXT.encode())
    assert first.status == "added" and first.chunks == 1
    assert detector.recently_added_chunks.signature_by_key == {}  # memory emptied once the batch was uploaded

    [second] = pipeline.ingest_file("incident_copy.txt", NEAR_COPY.encode())
    [skipped_chunk] = second.skipped_chunks
    assert skipped_chunk["duplicate_of"] == f"{first.doc_id}:0"  # found through Qdrant, not memory

