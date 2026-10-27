"""Stop button / closed tab: when the visitor disconnects from /ask/stream, the agent must stop spending LLM calls.

Uses a real uvicorn server on a free local port, because only a real server closes the stream when the client goes
away (TestClient doesn't model a disconnect). The LLM is a slow fake that counts its calls.
"""
import json
import socket
import threading
import time

import httpx
import uvicorn

from casefile.api.app import create_app
from casefile.api.services import AppServices
from casefile.ingestion.pipeline import IngestionPipeline
from casefile.rag.agent import InvestigationAgent
from casefile.rag.llm import LLMReply, ToolCall
from casefile.rag.tools import ToolExecutor
from casefile.retrieval.search import HybridSearcher

LLM_SECONDS_PER_CALL = 0.5


class SlowCountingLLM:
    model_name = "slow-fake"

    def __init__(self):
        self.calls = 0

    def generate(self, system_prompt, messages, tools):
        self.calls += 1
        time.sleep(LLM_SECONDS_PER_CALL)
        return LLMReply(text="", tool_calls=[ToolCall("search_documents", {"query": f"search {self.calls}"})])


def find_free_port():
    with socket.socket() as probe:
        probe.bind(("127.0.0.1", 0))
        return probe.getsockname()[1]


def test_disconnecting_stops_the_investigation(qdrant_store, embedder):
    llm = SlowCountingLLM()
    searcher = HybridSearcher(qdrant_store, embedder)
    agent = InvestigationAgent(llm, create_tool_executor=lambda: ToolExecutor(searcher, qdrant_store),
                               max_tool_steps=20)  # without a stop it would make 20+ LLM calls
    pipeline = IngestionPipeline(qdrant_store)
    pipeline.ingest_file("hotel.txt", b"The Lighthouse Hotel in Port Ellis was built in 1902 by Margaret Hale.")
    services = AppServices(store=qdrant_store, pipeline=pipeline, agent=agent, model_name="fake")
    port = find_free_port()
    server = uvicorn.Server(uvicorn.Config(create_app(services, questions_per_hour_per_visitor=0), port=port,
                                           log_level="warning"))
    threading.Thread(target=server.run, daemon=True).start()
    while not server.started:
        time.sleep(0.05)
    try:
        received_types = []
        with httpx.stream("POST", f"http://127.0.0.1:{port}/ask/stream", json={"question": "q"}, timeout=10) as response:
            for line in response.iter_lines():
                if line.startswith("data:"):
                    received_types.append(json.loads(line[5:])["type"])
                    if received_types[-1] == "tool_result":
                        break  # the visitor presses Stop after the first search: the connection closes here
        assert received_types == ["started", "tool_call", "tool_result"]  # a real search happened, no error
        calls_at_disconnect = llm.calls
        time.sleep(LLM_SECONDS_PER_CALL * 6)  # time for several more calls, if the agent kept going
        assert llm.calls <= calls_at_disconnect + 1  # at most the call already in progress finishes
    finally:
        server.should_exit = True
