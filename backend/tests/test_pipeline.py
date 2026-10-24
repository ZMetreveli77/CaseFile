from casefile.ingestion.pipeline import IngestionPipeline

TEXT = ("Incident report. The checkout API went down on March 3rd. Root cause was change CHG-42, "
        "which updated the load balancer timeout. Services affected: payments and invoicing.")


def test_add_unchanged_update_delete(store):
    p = IngestionPipeline(store, size=80)
    [r] = p.ingest_file("inc.txt", TEXT.encode())
    assert r.status == "added" and r.chunks > 0

    [r] = p.ingest_file("inc.txt", TEXT.encode())
    assert r.status == "unchanged"

    [r] = p.ingest_file("inc.txt", (TEXT + " Resolved on March 4th by rolling back CHG-42.").encode())
    assert r.status == "updated"
    assert "Resolved" in " ".join(c.text for c in store.chunks[r.doc_id])

    assert p.delete(r.doc_id) is True
    assert store.get_document(r.doc_id) is None
    assert p.delete(r.doc_id) is False


def test_same_content_under_other_name_is_duplicate(store):
    p = IngestionPipeline(store)
    [a] = p.ingest_file("a.txt", TEXT.encode())
    [b] = p.ingest_file("b.txt", TEXT.encode())
    assert b.status == "duplicate" and b.duplicate_of == a.doc_id


def test_near_duplicate_chunks_are_skipped(store):
    p = IngestionPipeline(store)
    p.ingest_file("a.txt", TEXT.encode())
    [b] = p.ingest_file("b.txt", (TEXT + " Extra line.").encode())
    assert b.status == "added" and b.chunks == 0 and len(b.skipped_chunks) == 1


def test_update_frees_old_chunks_for_dedup(store):
    p = IngestionPipeline(store)
    [a] = p.ingest_file("a.txt", TEXT.encode())
    p.delete(a.doc_id)
    [b] = p.ingest_file("b.txt", TEXT.encode())
    assert b.status == "added" and b.chunks == 1


def test_dedup_index_rebuilt_from_existing_store(store):
    IngestionPipeline(store).ingest_file("a.txt", TEXT.encode())
    fresh = IngestionPipeline(store)  # e.g. after app restart
    [b] = fresh.ingest_file("b.txt", (TEXT + " More.").encode())
    assert b.chunks == 0
