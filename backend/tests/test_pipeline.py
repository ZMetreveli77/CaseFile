import json

import pytest

from casefile.ingestion.dedup import DuplicateDetector
from casefile.ingestion.loaders import load_documents
from casefile.ingestion.pipeline import IngestionPipeline, ProtectedDocumentError

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


def make_corpus_documents(paragraph_count):
    records = [{"id": f"title {number}", "title": f"title {number}",
                "text": f"Paragraph {number} is about subject number {number} and nothing else at all."}
               for number in range(paragraph_count)]
    return load_documents("corpus.jsonl", "\n".join(json.dumps(record) for record in records).encode())


def test_batches_use_three_store_calls_and_keep_input_order(store):
    documents = make_corpus_documents(10)
    pipeline = IngestionPipeline(store)
    store.call_count = 0
    results = pipeline.ingest_documents(documents, batch_size=4)  # 3 batches: 4 + 4 + 2
    assert [result.doc_id for result in results] == [document.doc_id for document in documents]
    assert all(result.status == "added" for result in results)
    assert store.call_count == 3 * 3  # get_documents + find_by_hashes + upsert_many per batch


def test_same_content_twice_in_one_batch_is_a_duplicate(store):
    [first, second] = load_documents("pair.jsonl", (json.dumps({"id": "a", "text": INCIDENT_TEXT}) + "\n" +
                                                    json.dumps({"id": "b", "text": INCIDENT_TEXT})).encode())
    results = IngestionPipeline(store).ingest_documents([first, second])
    assert [result.status for result in results] == ["added", "duplicate"]
    assert results[1].duplicate_of == first.doc_id


def test_rerunning_a_batch_changes_nothing(store):
    documents = make_corpus_documents(5)
    pipeline = IngestionPipeline(store)
    pipeline.ingest_documents(documents)
    store.call_count = 0
    results = pipeline.ingest_documents(documents)
    assert all(result.status == "unchanged" for result in results)
    assert store.call_count == 2  # lookups only, no upsert (this is what makes the indexer resumable)


def test_pipeline_does_not_scan_the_store_when_given_a_detector(store, monkeypatch):
    def fail_if_scanned():
        raise AssertionError("should not scan: a detector passed in needs no rebuild")

    monkeypatch.setattr(store, "iter_chunks", fail_if_scanned)
    pipeline = IngestionPipeline(store, duplicate_detector=DuplicateDetector())  # would raise if it scanned
    [result] = pipeline.ingest_file("a.txt", INCIDENT_TEXT.encode())
    assert result.status == "added"


def is_from_corpus_file(document):
    return document.metadata.get("source", "").startswith("corpus.jsonl#")


def corpus_record(text):
    return (json.dumps({"id": "Flavian dynasty", "title": "Flavian dynasty", "text": text}) + "\n").encode()


def test_protected_documents_cannot_be_overwritten_by_reusing_their_name(store):
    """The public demo's corpus: an upload named corpus.jsonl gets the same document ids, so the stored document is
    checked, not the upload."""
    indexing_pipeline = IngestionPipeline(store)  # the indexing script protects nothing
    [original] = indexing_pipeline.ingest_file("corpus.jsonl", corpus_record("The Flavian dynasty ruled Rome."))
    public_pipeline = IngestionPipeline(store, is_protected=is_from_corpus_file)
    [attempt] = public_pipeline.ingest_file("corpus.jsonl", corpus_record("The Flavians never existed."))
    assert attempt.status == "protected" and attempt.doc_id == original.doc_id
    assert store.get_document(original.doc_id).text == "The Flavian dynasty ruled Rome."
    [same_again] = public_pipeline.ingest_file("corpus.jsonl", corpus_record("The Flavian dynasty ruled Rome."))
    assert same_again.status == "unchanged"  # nothing would change, so nothing to refuse


def test_protected_documents_cannot_be_deleted_but_others_can(store):
    [corpus_document] = IngestionPipeline(store).ingest_file("corpus.jsonl",
                                                             corpus_record("The Flavian dynasty ruled Rome."))
    public_pipeline = IngestionPipeline(store, is_protected=is_from_corpus_file)
    [own_upload] = public_pipeline.ingest_file("inc.txt", INCIDENT_TEXT.encode())
    with pytest.raises(ProtectedDocumentError):
        public_pipeline.delete(corpus_document.doc_id)
    assert store.get_document(corpus_document.doc_id) is not None
    assert public_pipeline.delete(own_upload.doc_id) is True
