"""API tests: real FastAPI app + in-memory Qdrant + fake embedder + scripted fake LLM (no network, no keys)."""
import json
import pytest
import time

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


def test_unsupported_file_type_is_415(client):
    response = upload(client, "image.png", "not really an image")
    assert response.status_code == 415
    assert ".png" in response.json()["detail"]


def test_too_large_upload_is_413(client, monkeypatch):
    monkeypatch.setattr("casefile.api.app.MAX_UPLOAD_BYTES", 10)
    response = upload(client, "big.txt", "x" * 11)
    assert response.status_code == 413
    assert client.get("/documents").json()["total"] == 0  # nothing was stored


@pytest.mark.parametrize("method, path, sends_file", [
    ("GET", "/documents/no-such-id", False),
    ("PUT", "/documents/no-such-id", True),
    ("DELETE", "/documents/no-such-id", False),
    ("GET", "/sources/no-such-chunk", False),
])
def test_unknown_id_is_404(client, method, path, sends_file):
    # PUT needs a file: without one FastAPI would answer 422 before our 404 check even runs.
    files = {"file": ("hotel.txt", HOTEL_TEXT.encode(), "text/plain")} if sends_file else None
    response = client.request(method, path, files=files)
    assert response.status_code == 404


def test_blank_question_is_422(client):
    assert client.post("/ask", json={"question": "   "}).status_code == 422


def test_file_with_only_spaces_is_422(client):
    response = upload(client, "empty.txt", "     ")
    assert response.status_code == 422
    assert "No text could be extracted" in response.json()["detail"]


def test_page_size_zero_is_422(client):
    assert client.get("/documents", params={"limit": 0}).status_code == 422


def read_sse_events(stream_text):
    """Parse an SSE body into (event name, data) pairs; each event ends with a blank line."""
    events = []
    for block in stream_text.strip().split("\n\n"):
        if block.startswith(":"):  # an SSE comment such as the keep-alive heartbeat: not an event
            continue
        name_line, data_line = block.split("\n")
        events.append((name_line.removeprefix("event: "), json.loads(data_line.removeprefix("data: "))))
    return events


def stream_ask(client, question):
    """POST /ask/stream and read the body piece by piece, as it arrives (like a browser would)."""
    with client.stream("POST", "/ask/stream", json={"question": question}) as response:
        body = "".join(response.iter_text())
    return response, body


def test_ask_stream_sends_progress_events_then_the_answer(qdrant_store, embedder):
    hotel_chunk_id = f"{create_document_id('hotel.txt')}:0"
    final_answer = {"answer": "Margaret Hale, in 1902", "should_abstain": False, "abstain_reason": "", "conflicts": [],
                    "claims": [{"text": "Built in 1902 by Margaret Hale.", "citations": [hotel_chunk_id]}]}
    replies = [LLMReply(text="", tool_calls=[ToolCall("search_documents", {"query": "Lighthouse Hotel builder"})]),
               LLMReply(text=json.dumps(final_answer))]
    with make_client(qdrant_store, embedder, replies) as client:
        upload(client, "hotel.txt", HOTEL_TEXT)
        response, body = stream_ask(client, "Who built the Lighthouse Hotel?")
    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/event-stream")
    assert response.headers["cache-control"] == "no-cache" and response.headers["x-accel-buffering"] == "no"

    events = read_sse_events(body)
    assert [name for name, _ in events] == ["started", "tool_call", "tool_result", "answer"]
    assert all(name == data["type"] for name, data in events)  # the SSE event name matches the JSON type
    assert events[2][1]["titles"] == ["hotel.txt"]
    final = events[-1][1]
    assert final["answer"] == "Margaret Hale, in 1902" and final["claims"][0]["citations"] == [hotel_chunk_id]


def test_ask_stream_turns_an_llm_outage_into_an_error_event(qdrant_store, embedder):
    with make_client(qdrant_store, embedder, [LLMError("Gave up after 5 attempts")]) as client:
        response, body = stream_ask(client, "Anything?")
    assert response.status_code == 200  # the stream had already started, so the error travels as an event
    event_names = [name for name, _ in read_sse_events(body)]
    assert event_names == ["started", "error"]
    assert "answer" not in event_names  # an error replaces the answer, it never comes in addition to it
    assert "unavailable" in read_sse_events(body)[-1][1]["detail"]


def test_ask_stream_rejects_a_blank_question(client):
    assert client.post("/ask/stream", json={"question": "   "}).status_code == 422


def test_ask_stream_sends_keep_alive_comments_while_the_llm_is_slow(qdrant_store, embedder, monkeypatch):
    monkeypatch.setattr("casefile.api.app.HEARTBEAT_SECONDS", 0.05)  # instead of 15 s, so the test stays fast
    original_generate = FakeLLM.generate

    def slow_generate(self, *arguments):
        time.sleep(0.3)  # a slow model / retries: several heartbeat intervals without any event
        return original_generate(self, *arguments)

    monkeypatch.setattr(FakeLLM, "generate", slow_generate)
    final_answer = {"answer": "", "claims": [], "conflicts": [], "should_abstain": True, "abstain_reason": "none"}
    with make_client(qdrant_store, embedder, [LLMReply(text=json.dumps(final_answer))]) as client:
        _, body = stream_ask(client, "Anything?")
    assert ": keep-alive" in body
    assert [name for name, _ in read_sse_events(body)] == ["started", "answer"]  # comments are not events