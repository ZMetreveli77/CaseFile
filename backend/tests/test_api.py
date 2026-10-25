"""API tests: real FastAPI app + in-memory Qdrant + fake embedder + scripted fake LLM (no network, no keys)."""
import json

import pytest
from fastapi.testclient import TestClient

from casefile.api.app import create_app
from casefile.api.services import AppServices
from casefile.ingestion.loaders import create_document_id
from casefile.ingestion.pipeline import IngestionPipeline
from casefile.rag.agent import InvestigationAgent
from casefile.rag.llm import LLMError, LLMReply, ToolCall
from casefile.rag.tools import ToolExecutor
from casefile.retrieval.search import HybridSearcher
from tests.fakes import FakeLLM

HOTEL_TEXT = "The Lighthouse Hotel in Port Ellis was built in 1902 by Margaret Hale."


def make_client(qdrant_store, embedder, llm_replies=()):
    searcher = HybridSearcher(qdrant_store, embedder)
    agent = InvestigationAgent(FakeLLM(llm_replies), create_tool_executor=lambda: ToolExecutor(searcher, qdrant_store))
    services = AppServices(store=qdrant_store, pipeline=IngestionPipeline(qdrant_store), agent=agent,
                           model_name="fake")
    return TestClient(create_app(services))


@pytest.fixture
def client(qdrant_store, embedder):
    with make_client(qdrant_store, embedder) as test_client:
        yield test_client


def upload(client, file_name, text):
    return client.post("/documents", files={"file": (file_name, text.encode(), "text/plain")})


def test_health_reports_counts(client):
    upload(client, "hotel.txt", HOTEL_TEXT)
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok", "model": "fake", "documents": 1, "chunks": 1}


def test_upload_then_get_list_source_and_delete(client):
    response = upload(client, "hotel.txt", HOTEL_TEXT)
    assert response.status_code == 201
    [result] = response.json()["results"]
    assert result["status"] == "added" and result["chunks"] == 1
    doc_id = result["doc_id"]

    document = client.get(f"/documents/{doc_id}").json()
    assert document["title"] == "hotel.txt" and document["characters"] == len(HOTEL_TEXT)
    listing = client.get("/documents").json()
    assert listing["total"] == 1 and listing["documents"][0]["doc_id"] == doc_id
    source = client.get(f"/sources/{doc_id}:0").json()
    assert source["text"] == HOTEL_TEXT and source["doc_id"] == doc_id

    assert client.delete(f"/documents/{doc_id}").status_code == 204
    assert client.get("/documents").json()["total"] == 0


def test_same_upload_twice_is_unchanged(client):
    upload(client, "hotel.txt", HOTEL_TEXT)
    [result] = upload(client, "hotel.txt", HOTEL_TEXT).json()["results"]
    assert result["status"] == "unchanged"


def test_put_replaces_document_content_and_keeps_its_id(client):
    [added] = upload(client, "hotel.txt", HOTEL_TEXT).json()["results"]
    response = client.put(f"/documents/{added['doc_id']}",
                          files={"file": ("new_version.txt", b"The hotel was renovated in 1999.", "text/plain")})
    assert response.status_code == 200 and response.json()["status"] == "updated"
    assert response.json()["doc_id"] == added["doc_id"]
    assert "renovated" in client.get(f"/sources/{added['doc_id']}:0").json()["text"]


def test_document_listing_is_paged(client):
    for number in range(5):
        upload(client, f"note{number}.txt", f"Note number {number} about subject {number}.")
    first_page = client.get("/documents", params={"limit": 2}).json()
    assert len(first_page["documents"]) == 2 and first_page["next_cursor"] and first_page["total"] == 5
    second_page = client.get("/documents", params={"limit": 2, "cursor": first_page["next_cursor"]}).json()
    first_ids = {document["doc_id"] for document in first_page["documents"]}
    assert first_ids.isdisjoint(document["doc_id"] for document in second_page["documents"])


def test_ask_returns_a_cited_answer(qdrant_store, embedder):
    hotel_chunk_id = f"{create_document_id('hotel.txt')}:0"
    final_answer = {"answer": "Margaret Hale, in 1902", "should_abstain": False, "abstain_reason": "", "conflicts": [],
                    "claims": [{"text": "Built in 1902 by Margaret Hale.", "citations": [hotel_chunk_id]}]}
    replies = [LLMReply(text="", tool_calls=[ToolCall("search_documents", {"query": "Lighthouse Hotel builder"})]),
               LLMReply(text=json.dumps(final_answer))]
    with make_client(qdrant_store, embedder, replies) as client:
        upload(client, "hotel.txt", HOTEL_TEXT)
        response = client.post("/ask", json={"question": "Who built the Lighthouse Hotel?"})
    body = response.json()
    assert response.status_code == 200 and body["answer"] == "Margaret Hale, in 1902"
    assert body["claims"][0]["citations"] == [hotel_chunk_id]
    assert body["source_titles"][hotel_chunk_id] == "hotel.txt"
    assert body["search_queries"] == ["Lighthouse Hotel builder"]


def test_llm_outage_becomes_503(qdrant_store, embedder):
    with make_client(qdrant_store, embedder, [LLMError("Gave up after 5 attempts")]) as client:
        response = client.post("/ask", json={"question": "Anything?"})
    assert response.status_code == 503 and "unavailable" in response.json()["detail"]


def test_supported_formats_are_listed(client):
    assert ".pdf" in client.get("/formats").json()["extensions"]
