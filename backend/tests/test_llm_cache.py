from google.genai import types

from casefile.rag.llm import GeminiProvider, LLMReply, Message, ToolCall, ToolSpec
from casefile.rag.llm_cache import CachingLLM
from tests.fakes import FakeLLM

SEARCH = ToolSpec("search_documents", "Search.", {"type": "object"})


def test_second_identical_call_is_replayed_from_disk(tmp_path):
    inner = FakeLLM([LLMReply(text="", tool_calls=[ToolCall("search_documents", {"query": "q"})])])
    cached = CachingLLM(inner, tmp_path)
    messages = [Message(role="user", text="Who built it?")]
    first = cached.generate("system", messages, [SEARCH])
    second = cached.generate("system", messages, [SEARCH])  # FakeLLM has no reply left: this must come from disk
    assert second.tool_calls == first.tool_calls == [ToolCall("search_documents", {"query": "q"})]
    assert (cached.misses, cached.hits) == (1, 1) and len(inner.requests) == 1


def test_any_change_in_the_request_is_a_new_call(tmp_path):
    cached = CachingLLM(FakeLLM([LLMReply(text="a"), LLMReply(text="b"), LLMReply(text="c")]), tmp_path)
    question = [Message(role="user", text="Who built it?")]
    tool_turn = question + [Message(role="tool", tool_name="search_documents", tool_result={"results": [1]})]
    replies = [cached.generate("system", question, [SEARCH]).text,
               cached.generate("other system", question, [SEARCH]).text,
               cached.generate("system", tool_turn, [SEARCH]).text]
    assert replies == ["a", "b", "c"] and cached.misses == 3


def test_gemini_thought_signatures_survive_the_cache(tmp_path):
    provider = GeminiProvider(api_key="test-key", model_name="test-model", timeout_seconds=1)
    content = types.Content(role="model", parts=[types.Part(
        function_call=types.FunctionCall(name="search_documents", args={"query": "q"}), thought_signature=b"\x00secret\xff")])
    provider.generate = lambda system_prompt, messages, tools: LLMReply(
        text="", tool_calls=[ToolCall("search_documents", {"query": "q"})], provider_content=content)
    cached = CachingLLM(provider, tmp_path)
    cached.generate("system", [Message(role="user", text="q")], [SEARCH])
    replayed = cached.generate("system", [Message(role="user", text="q")], [SEARCH])
    assert replayed.provider_content.parts[0].thought_signature == b"\x00secret\xff"
    assert cached.hits == 1
