from casefile.ingestion.chunking import chunk_document
from casefile.ingestion.loaders import load_documents
from casefile.ingestion.pipeline import IngestionPipeline
from casefile.retrieval import bm25

INCIDENT_TEXT = ("Incident report. The checkout API went down on March 3rd. Root cause was change CHG-42, "
                 "which updated the load balancer timeout. Services affected: payments and invoicing.")
UNRELATED_TEXT = "Team offsite notes. We discussed hiring plans and the office move to a new building in May."


def store_text(qdrant_store, file_name, text):
    [document] = load_documents(file_name, text.encode())
    qdrant_store.upsert(document, chunk_document(document, max_characters=100))
    return document


def test_upsert_get_find_and_list(qdrant_store):
    document = store_text(qdrant_store, "inc.txt", INCIDENT_TEXT)
    stored = qdrant_store.get_document(document.doc_id)
    assert stored.content_hash == document.content_hash and stored.title == "inc.txt"
    assert qdrant_store.find_by_hash(document.content_hash).doc_id == document.doc_id
    assert qdrant_store.find_by_hash("no-such-hash") is None

    [listed], next_cursor = qdrant_store.list_documents_page(limit=10)
    assert listed["doc_id"] == document.doc_id and listed["chunk_count"] > 1 and "text" not in listed
    assert next_cursor is None and qdrant_store.count_documents() == 1


def test_document_pages_cover_everything_once(qdrant_store):
    stored_ids = {store_text(qdrant_store, f"note{number}.txt", f"Note number {number} about topic {number}.").doc_id
                  for number in range(5)}
    seen_ids, cursor = [], None
    while True:
        page, cursor = qdrant_store.list_documents_page(limit=2, cursor=cursor)
        assert len(page) <= 2
        seen_ids += [document["doc_id"] for document in page]
        if cursor is None:
            break
    assert sorted(seen_ids) == sorted(stored_ids)  # every document exactly once


def test_iter_chunks_get_chunk_and_delete(qdrant_store):
    first = store_text(qdrant_store, "inc.txt", INCIDENT_TEXT)
    second = store_text(qdrant_store, "notes.txt", UNRELATED_TEXT)
    first_chunks = list(qdrant_store.iter_chunks(first.doc_id))
    assert first_chunks and all(chunk.doc_id == first.doc_id for chunk in first_chunks)
    assert qdrant_store.get_chunk(first_chunks[0].chunk_id).text == first_chunks[0].text

    removed_chunk_ids = qdrant_store.delete(first.doc_id)
    assert sorted(removed_chunk_ids) == sorted(chunk.chunk_id for chunk in first_chunks)
    assert qdrant_store.get_document(first.doc_id) is None
    assert {chunk.doc_id for chunk in qdrant_store.iter_chunks()} == {second.doc_id}


def test_sparse_search_finds_exact_id(qdrant_store):
    store_text(qdrant_store, "inc.txt", INCIDENT_TEXT)
    store_text(qdrant_store, "notes.txt", UNRELATED_TEXT)
    [top_result, *_] = qdrant_store.search_sparse(bm25.encode_query("CHG-42"), limit=5)
    assert "CHG-42" in top_result.chunk.text
    assert qdrant_store.search_sparse(bm25.encode_query("the of"), limit=5) == []


def test_dense_search_ranks_related_text_first(qdrant_store, embedder):
    store_text(qdrant_store, "inc.txt", INCIDENT_TEXT)
    store_text(qdrant_store, "notes.txt", UNRELATED_TEXT)
    [top_result, *_] = qdrant_store.search_dense(embedder.embed_query("hiring plans office move"), limit=5)
    assert "hiring" in top_result.chunk.text


def test_batch_methods_and_count(qdrant_store):
    first = store_text(qdrant_store, "inc.txt", INCIDENT_TEXT)
    second = store_text(qdrant_store, "notes.txt", UNRELATED_TEXT)
    found_by_id = qdrant_store.get_documents([first.doc_id, second.doc_id, "missing"])
    assert set(found_by_id) == {first.doc_id, second.doc_id}
    found_by_hash = qdrant_store.find_by_hashes([second.content_hash, "no-such-hash"])
    assert found_by_hash[second.content_hash].doc_id == second.doc_id and len(found_by_hash) == 1
    assert qdrant_store.get_documents([]) == {} and qdrant_store.find_by_hashes([]) == {}
    assert qdrant_store.count_chunks() == len(list(qdrant_store.iter_chunks()))


def test_pipeline_works_with_qdrant_store(qdrant_store):
    pipeline = IngestionPipeline(qdrant_store, max_characters=100)
    [added] = pipeline.ingest_file("inc.txt", INCIDENT_TEXT.encode())
    [updated] = pipeline.ingest_file("inc.txt", (INCIDENT_TEXT + " Rolled back on March 4th.").encode())
    assert added.status == "added" and updated.status == "updated"
    assert any("Rolled back" in chunk.text for chunk in qdrant_store.iter_chunks(updated.doc_id))
    assert pipeline.delete(updated.doc_id) is True
    assert list(qdrant_store.iter_chunks()) == []
