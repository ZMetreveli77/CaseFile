import pytest

from casefile.ingestion.pipeline import IngestionPipeline
from casefile.rag import tools
from casefile.rag.llm import ToolCall
from casefile.rag.tools import ToolExecutor
from casefile.retrieval.search import HybridSearcher

CORPUS = {
    "kiss.txt": "Kiss and Tell is a 1945 comedy film starring Shirley Temple as Corliss Archer.",
    "temple.txt": "Shirley Temple later served as Chief of Protocol of the United States.",
    "offsite.txt": "Team offsite notes about hiring plans and the office move.",
}


@pytest.fixture
def executor(qdrant_store, embedder):
    pipeline = IngestionPipeline(qdrant_store)
    for file_name, text in CORPUS.items():
        pipeline.ingest_file(file_name, text.encode())
    return ToolExecutor(HybridSearcher(qdrant_store, embedder), qdrant_store, results_per_call=2)


def test_search_returns_citable_results_and_logs_evidence(executor):
    result = executor.execute(ToolCall("search_documents", {"query": "Shirley Temple Chief of Protocol"}))
    [first, *_] = result["results"]
    assert set(first) == {"chunk_id", "doc_id", "title", "text"}
    assert "Protocol" in first["text"]
    assert set(executor.retrieved_chunks) == {item["chunk_id"] for item in result["results"]}
    assert executor.search_queries == ["Shirley Temple Chief of Protocol"]


def test_read_document_returns_its_passages(executor):
    doc_id = executor.execute(ToolCall("search_documents", {"query": "Kiss and Tell"}))["results"][0]["doc_id"]
    result = executor.execute(ToolCall("read_document", {"doc_id": doc_id}))
    assert result["doc_id"] == doc_id and result["passages"] and result["truncated"] is False


def test_read_document_only_logs_passages_that_were_shown(executor, monkeypatch):
    monkeypatch.setattr(tools, "MAX_DOCUMENT_CHARACTERS", 1)  # too small for any passage
    doc_id = executor.execute(ToolCall("search_documents", {"query": "Kiss and Tell"}))["results"][0]["doc_id"]
    logged_before = set(executor.retrieved_chunks)
    result = executor.execute(ToolCall("read_document", {"doc_id": doc_id}))
    assert result["passages"] == [] and result["truncated"] is True
    assert set(executor.retrieved_chunks) == logged_before


def test_mistakes_become_error_results(executor):
    assert "error" in executor.execute(ToolCall("delete_everything", {}))
    assert "error" in executor.execute(ToolCall("search_documents", {"query": "  "}))
    assert "error" in executor.execute(ToolCall("read_document", {"doc_id": "no-such-doc"}))
    assert executor.retrieved_chunks == {}
