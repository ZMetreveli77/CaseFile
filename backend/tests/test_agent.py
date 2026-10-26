import json

import pytest

from casefile.rag.agent import INVALID_FORMAT_REASON, InvestigationAgent, describe_tool_result, extract_json_object
from casefile.models import Chunk
from casefile.rag.llm import LLMError, LLMReply, ToolCall
from casefile.rag.prompts import FINAL_ANSWER_REMINDER
from tests.fakes import FakeLLM


class FakeToolExecutor:
    """Stands in for ToolExecutor: every search 'finds' one chunk named after the query."""

    def __init__(self):
        self.retrieved_chunks = {}
        self.search_queries = []

    def execute(self, tool_call):
        query = tool_call.arguments["query"]
        self.search_queries.append(query)
        chunk_id = f"chunk-{len(self.search_queries)}"
        self.retrieved_chunks[chunk_id] = Chunk(chunk_id=chunk_id, doc_id="doc", index=0, text="", title=query)
        return {"results": [{"chunk_id": chunk_id, "title": query, "text": f"text about {query}"}]}


def keep_answer_as_is(answer, retrieved_chunk_ids):
    return answer


def final_json(**fields):
    answer = {"answer": "", "claims": [], "conflicts": [], "should_abstain": False, "abstain_reason": ""}
    answer.update(fields)
    return LLMReply(text=json.dumps(answer))


def search(query):
    return LLMReply(text="", tool_calls=[ToolCall("search_documents", {"query": query})])


def make_agent(replies, **options):
    llm = FakeLLM(replies)
    agent = InvestigationAgent(llm, FakeToolExecutor, validate_citations=keep_answer_as_is, **options)
    return agent, llm


def test_two_searches_then_cited_answer():
    agent, llm = make_agent([
        search("Kiss and Tell 1945 film Corliss Archer"),
        search("Shirley Temple government position"),
        final_json(answer="Chief of Protocol",
                   claims=[{"text": "Shirley Temple played Corliss Archer.", "citations": ["chunk-1"]},
                           {"text": "She was Chief of Protocol.", "citations": ["chunk-2"]}]),
    ])
    answer = agent.answer("What government position was held by the woman who portrayed Corliss Archer?")
    assert answer.answer == "Chief of Protocol" and not answer.should_abstain
    assert [claim.citations for claim in answer.claims] == [["chunk-1"], ["chunk-2"]]
    assert answer.search_queries == ["Kiss and Tell 1945 film Corliss Archer", "Shirley Temple government position"]
    assert answer.retrieved_chunk_ids == ["chunk-1", "chunk-2"] and answer.llm_calls == 3
    assert answer.source_titles == {"chunk-1": "Kiss and Tell 1945 film Corliss Archer",
                                    "chunk-2": "Shirley Temple government position"}


def test_tool_results_are_sent_back_to_the_llm():
    agent, llm = make_agent([search("first query"), final_json(answer="done")])
    agent.answer("question")
    second_request_messages, _ = llm.requests[1]
    tool_message = second_request_messages[-1]
    assert tool_message.role == "tool" and tool_message.tool_name == "search_documents"
    assert tool_message.tool_result["results"][0]["chunk_id"] == "chunk-1"


def test_step_limit_forces_a_final_answer_without_tools():
    agent, llm = make_agent([search("a"), search("b"), final_json(answer="best effort")], max_tool_steps=2)
    answer = agent.answer("question")
    final_messages, final_tools = llm.requests[-1]
    assert final_tools == []  # no tools allowed on the forced final call
    assert final_messages[-1].text == FINAL_ANSWER_REMINDER
    assert answer.answer == "best effort" and answer.llm_calls == 3


def test_unparseable_final_reply_becomes_an_abstention():
    agent, _ = make_agent([LLMReply(text="I think the answer is probably Paris.")])
    answer = agent.answer("question")
    assert answer.should_abstain and answer.abstain_reason == INVALID_FORMAT_REASON
    assert answer.answer == "" and answer.claims == []


def test_json_inside_markdown_fences_is_accepted():
    fenced = LLMReply(text='Here you go:\n```json\n{"answer": "yes", "claims": []}\n```')
    agent, _ = make_agent([fenced])
    assert agent.answer("question").answer == "yes"


def test_llm_failure_is_raised_not_hidden():
    agent, _ = make_agent([LLMError("Gemini error 401: bad key")])
    with pytest.raises(LLMError):
        agent.answer("question")


def test_citation_validator_receives_the_evidence_log():
    seen = {}

    def record_validator(answer, retrieved_chunk_ids):
        seen["ids"] = retrieved_chunk_ids
        return answer

    llm = FakeLLM([search("q"), final_json(answer="x")])
    InvestigationAgent(llm, FakeToolExecutor, validate_citations=record_validator).answer("question")
    assert seen["ids"] == {"chunk-1"}


def test_extract_json_object_rejects_non_objects():
    with pytest.raises(ValueError):
        extract_json_object("no json here")
    with pytest.raises(ValueError):
        extract_json_object("[1, 2]")


def test_progress_events_come_in_order_and_are_json_serializable():
    agent, _ = make_agent([search("Kiss and Tell 1945 film"), search("Shirley Temple"), final_json(answer="x")])
    collected = []
    agent.answer("Who?", on_event=collected.append)
    assert [event["type"] for event in collected] == ["started", "tool_call", "tool_result", "tool_call", "tool_result"]
    assert collected[0] == {"type": "started", "question": "Who?"}
    assert collected[1] == {"type": "tool_call", "tool": "search_documents",
                            "arguments": {"query": "Kiss and Tell 1945 film"}}
    assert collected[2] == {"type": "tool_result", "tool": "search_documents",
                            "titles": ["Kiss and Tell 1945 film"], "error": None}
    json.dumps(collected)  # raises TypeError if any event is not JSON-serializable


def test_tool_error_is_reported_in_the_event():
    assert describe_tool_result("read_document", {"error": "No document with doc_id 'x'."}) == {
        "type": "tool_result", "tool": "read_document", "titles": [], "error": "No document with doc_id 'x'."}


def test_a_failing_progress_callback_does_not_break_the_answer():
    def broken_display(event):
        raise RuntimeError("browser disconnected")

    agent, _ = make_agent([search("q"), final_json(answer="still answered")])
    assert agent.answer("question", on_event=broken_display).answer == "still answered"