import pytest

from casefile.ingestion.pipeline import IngestionPipeline
from casefile.retrieval.search import HybridSearcher

CORPUS = {
    "incident.txt": "The checkout API went down on March 3rd. Root cause was change CHG-42 to the load balancer.",
    "changes.txt": "Change log. CHG-42 raised the load balancer timeout. CHG-43 updated the invoice template.",
    "services.txt": "Payments and invoicing depend on the checkout API. Invoicing retries failed requests.",
    "offsite.txt": "Team offsite notes. We discussed hiring plans and the office move in May.",
}


@pytest.fixture
def filled_store(qdrant_store):
    pipeline = IngestionPipeline(qdrant_store)
    for file_name, text in CORPUS.items():
        pipeline.ingest_file(file_name, text.encode())
    return qdrant_store


@pytest.mark.parametrize("mode", ["dense", "hybrid", "hybrid_rerank"])
def test_every_mode_returns_relevant_results(filled_store, embedder, mode):
    searcher = HybridSearcher(filled_store, embedder, mode=mode)
    results = searcher.search("What did CHG-42 change?", top_k=3)
    assert 0 < len(results) <= 3
    assert "CHG-42" in results[0].chunk.text
    assert all("offsite" not in result.chunk.text.lower() for result in results[:2])


def test_hybrid_records_where_each_result_came_from(filled_store, embedder):
    results = HybridSearcher(filled_store, embedder, mode="hybrid").search("CHG-42 load balancer", top_k=3)
    assert "dense_rank" in results[0].details and "sparse_rank" in results[0].details


def test_rerank_spreads_results_across_documents(filled_store, embedder):
    results = HybridSearcher(filled_store, embedder, mode="hybrid_rerank").search("checkout API CHG-42", top_k=3)
    assert len({result.chunk.doc_id for result in results}) == 3


def test_invalid_mode_and_empty_query(filled_store, embedder):
    with pytest.raises(ValueError):
        HybridSearcher(filled_store, embedder, mode="magic")
    assert HybridSearcher(filled_store, embedder).search("   ") == []
