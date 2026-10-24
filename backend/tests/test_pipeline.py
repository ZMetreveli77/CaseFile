from casefile.ingestion.pipeline import IngestionPipeline

INCIDENT_TEXT = ("Incident report. The checkout API went down on March 3rd. Root cause was change CHG-42, "
                 "which updated the load balancer timeout. Services affected: payments and invoicing.")


def test_add_unchanged_update_delete(store):
    pipeline = IngestionPipeline(store, max_characters=80)
    [result] = pipeline.ingest_file("inc.txt", INCIDENT_TEXT.encode())
    assert result.status == "added" and result.chunks > 0

    [result] = pipeline.ingest_file("inc.txt", INCIDENT_TEXT.encode())
    assert result.status == "unchanged"

    updated_text = INCIDENT_TEXT + " Resolved on March 4th by rolling back CHG-42."
    [result] = pipeline.ingest_file("inc.txt", updated_text.encode())
    assert result.status == "updated"
    assert "Resolved" in " ".join(chunk.text for chunk in store.chunks_by_doc_id[result.doc_id])

    assert pipeline.delete(result.doc_id) is True
    assert store.get_document(result.doc_id) is None
    assert pipeline.delete(result.doc_id) is False


def test_same_content_under_other_name_is_duplicate(store):
    pipeline = IngestionPipeline(store)
    [first_result] = pipeline.ingest_file("a.txt", INCIDENT_TEXT.encode())
    [second_result] = pipeline.ingest_file("b.txt", INCIDENT_TEXT.encode())
    assert second_result.status == "duplicate" and second_result.duplicate_of == first_result.doc_id


def test_near_duplicate_chunks_are_skipped(store):
    pipeline = IngestionPipeline(store)
    pipeline.ingest_file("a.txt", INCIDENT_TEXT.encode())
    [result] = pipeline.ingest_file("b.txt", (INCIDENT_TEXT + " Extra line.").encode())
    assert result.status == "added" and result.chunks == 0 and len(result.skipped_chunks) == 1


def test_delete_frees_old_chunks_for_dedup(store):
    pipeline = IngestionPipeline(store)
    [first_result] = pipeline.ingest_file("a.txt", INCIDENT_TEXT.encode())
    pipeline.delete(first_result.doc_id)
    [second_result] = pipeline.ingest_file("b.txt", INCIDENT_TEXT.encode())
    assert second_result.status == "added" and second_result.chunks == 1


def test_duplicate_index_rebuilt_from_existing_store(store):
    IngestionPipeline(store).ingest_file("a.txt", INCIDENT_TEXT.encode())
    restarted_pipeline = IngestionPipeline(store)  # e.g. after app restart
    [result] = restarted_pipeline.ingest_file("b.txt", (INCIDENT_TEXT + " More.").encode())
    assert result.chunks == 0
