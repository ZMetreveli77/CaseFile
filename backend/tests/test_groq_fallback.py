"""Groq provider (fake HTTP transport, no key or network) and the Gemini -> Groq failsafe."""
import json

import httpx
import pytest
from google.genai import types

from casefile.config import Settings
from casefile.rag.llm import (GROQ_CHAT_URL, MAX_RETRY_AFTER_SECONDS, FallbackProvider, GeminiProvider, GroqProvider,
                              LLMError, LLMReply, Message, RetryableLLMError, ToolCall, ToolSpec,
                              convert_messages_to_openai_format, translate_groq_error)
from casefile.rag.setup import build_llm
from tests.fakes import FakeLLM

SEARCH_TOOL = ToolSpec("search_documents", "Search.", {"type": "object", "properties": {"query": {"type": "string"}}})


# ---- message conversion ----

def test_tool_results_are_linked_to_their_calls_by_id_in_order():
    messages = [
        Message(role="user", text="question"),
        Message(role="assistant", tool_calls=[ToolCall("search_documents", {"query": "a"}),
                                              ToolCall("search_documents", {"query": "b"})]),
        Message(role="tool", tool_name="search_documents", tool_result={"results": ["a"]}),
        Message(role="tool", tool_name="search_documents", tool_result={"results": ["b"]}),
        Message(role="assistant", tool_calls=[ToolCall("read_document", {"doc_id": "d"})]),
        Message(role="tool", tool_name="read_document", tool_result={"text": "d"}),
    ]
    converted = convert_messages_to_openai_format("rules", messages)
    assert converted[0] == {"role": "system", "content": "rules"}
    assert [call["id"] for call in converted[2]["tool_calls"]] == ["call_0", "call_1"]
    assert json.loads(converted[2]["tool_calls"][0]["function"]["arguments"]) == {"query": "a"}
    assert [converted[3]["tool_call_id"], converted[4]["tool_call_id"]] == ["call_0", "call_1"]
    assert json.loads(converted[4]["content"]) == {"results": ["b"]}
    assert converted[5]["tool_calls"][0]["id"] == "call_2" and converted[6]["tool_call_id"] == "call_2"


def test_a_conversation_started_on_gemini_continues_on_groq():
    """The failsafe can take over mid-investigation: Gemini's reply objects are ignored, the neutral fields are used."""
    gemini_content = types.Content(role="model", parts=[types.Part(text="Gemini-only object")])
    messages = [Message(role="user", text="question"),
                Message(role="assistant", text="Let me search.", provider_content=gemini_content,
                        tool_calls=[ToolCall("search_documents", {"query": "Shirley Temple"})]),
                Message(role="tool", tool_name="search_documents", tool_result={"results": []})]
    converted = convert_messages_to_openai_format("rules", messages)
    assert converted[2]["content"] == "Let me search."
    assert converted[2]["tool_calls"][0]["function"]["name"] == "search_documents"
    assert converted[3]["role"] == "tool" and converted[3]["tool_call_id"] == "call_0"
    assert "Gemini-only object" not in json.dumps(converted)


def test_empty_assistant_turns_are_left_out_and_orphan_tool_results_are_an_error():
    converted = convert_messages_to_openai_format("rules", [Message(role="user", text="q"), Message(role="assistant")])
    assert [message["role"] for message in converted] == ["system", "user"]
    with pytest.raises(LLMError):
        convert_messages_to_openai_format("rules", [Message(role="tool", tool_name="search_documents", tool_result={})])


# ---- errors ----

@pytest.mark.parametrize("status_code", [429, 500, 502, 503, 504])
def test_temporary_groq_errors_are_retryable(status_code):
    assert isinstance(translate_groq_error(status_code, "{}", None), RetryableLLMError)


@pytest.mark.parametrize("status_code", [400, 401, 404, 413])
def test_permanent_groq_errors_are_not_retryable(status_code):
    error = translate_groq_error(status_code, '{"error": {"message": "bad"}}', None)
    assert isinstance(error, LLMError) and not isinstance(error, RetryableLLMError)
    assert "Groq error" in str(error) and "bad" in str(error)


def test_a_malformed_tool_call_is_retried_unlike_other_bad_requests():
    body = '{"error": {"message": "attempted to call tool \'json\'", "code": "tool_use_failed"}}'
    assert isinstance(translate_groq_error(400, body, None), RetryableLLMError)


def test_groq_retry_after_header_is_used_and_a_daily_limit_fails_at_once():
    assert translate_groq_error(429, "{}", "7").retry_after_seconds == 7.0
    daily_limit = translate_groq_error(429, "{}", str(MAX_RETRY_AFTER_SECONDS + 1))
    assert isinstance(daily_limit, LLMError) and not isinstance(daily_limit, RetryableLLMError)


# ---- the provider, over a fake HTTP transport ----

def make_groq_provider(handle_request):
    return GroqProvider(api_key="test-key", model_name="test-model", timeout_seconds=1,
                        call_with_retries=lambda action: action(),
                        http_client=httpx.Client(transport=httpx.MockTransport(handle_request)))


def test_groq_request_and_tool_call_reply():
    sent_requests = []

    def handle_request(request):
        sent_requests.append(request)
        return httpx.Response(200, json={"choices": [{"message": {"role": "assistant", "content": None, "tool_calls": [
            {"id": "x", "type": "function",
             "function": {"name": "search_documents", "arguments": '{"query": "Kiss and Tell"}'}}]}}]})

    reply = make_groq_provider(handle_request).generate("rules", [Message(role="user", text="q")], [SEARCH_TOOL])
    assert reply == LLMReply(text="", tool_calls=[ToolCall("search_documents", {"query": "Kiss and Tell"})])
    request_body = json.loads(sent_requests[0].content)
    assert str(sent_requests[0].url) == GROQ_CHAT_URL
    assert sent_requests[0].headers["authorization"] == "Bearer test-key"
    assert request_body["model"] == "test-model" and request_body["temperature"] == 0
    assert request_body["tools"][0]["function"]["name"] == "search_documents"


def test_groq_text_reply_and_no_tools_field_without_tools():
    def handle_request(request):
        assert "tools" not in json.loads(request.content)
        return httpx.Response(200, json={"choices": [{"message": {"content": '{"answer": "yes"}'}}]})

    assert make_groq_provider(handle_request).generate("rules", [], []).text == '{"answer": "yes"}'


def test_groq_http_errors_and_bad_replies_become_llm_errors():
    rate_limited = make_groq_provider(lambda request: httpx.Response(429, headers={"retry-after": "3"}, json={}))
    with pytest.raises(RetryableLLMError):
        rate_limited.generate("rules", [], [])
    bad_arguments = make_groq_provider(lambda request: httpx.Response(200, json={"choices": [{"message": {
        "tool_calls": [{"function": {"name": "search_documents", "arguments": "{not json"}}]}}]}))
    with pytest.raises(LLMError):
        bad_arguments.generate("rules", [], [SEARCH_TOOL])
    with pytest.raises(LLMError):
        make_groq_provider(lambda request: httpx.Response(200, json={"choices": []})).generate("rules", [], [])


def test_groq_timeout_is_retryable():
    def handle_request(request):
        raise httpx.ReadTimeout("slow", request=request)

    with pytest.raises(RetryableLLMError):
        make_groq_provider(handle_request).generate("rules", [], [])


def test_missing_groq_key_fails_fast():
    with pytest.raises(LLMError):
        GroqProvider(api_key="", model_name="any", timeout_seconds=1)


# ---- the failsafe ----

class FakeClock:
    def __init__(self):
        self.now = 0.0

    def __call__(self):
        return self.now


def make_named_llm(name, replies):
    llm = FakeLLM(replies)
    llm.model_name = name
    return llm


def test_backup_is_not_called_while_the_primary_works():
    primary, backup = make_named_llm("gemini", [LLMReply(text="from gemini")]), make_named_llm("groq", [])
    reply = FallbackProvider(primary, backup).generate("rules", [], [])
    assert reply.text == "from gemini" and reply.fallback_reason == "" and backup.requests == []


def test_backup_answers_when_the_primary_fails_and_says_why():
    primary = make_named_llm("gemini", [LLMError("Gemini error 429: daily quota")])
    backup = make_named_llm("groq", [LLMReply(text="from groq")])
    reply = FallbackProvider(primary, backup).generate("rules", [], [])
    assert reply.text == "from groq"
    assert "gemini was unavailable (Gemini error 429: daily quota)" in reply.fallback_reason
    assert "backup model groq" in reply.fallback_reason


def test_primary_is_skipped_during_the_cooldown_then_tried_again():
    clock = FakeClock()
    primary = make_named_llm("gemini", [LLMError("down"), LLMReply(text="gemini is back")])
    backup = make_named_llm("groq", [LLMReply(text="groq 1"), LLMReply(text="groq 2")])
    failsafe = FallbackProvider(primary, backup, cooldown_seconds=600, clock=clock)
    assert failsafe.generate("rules", [], []).text == "groq 1"
    clock.now = 599
    assert failsafe.generate("rules", [], []).text == "groq 2"
    assert len(primary.requests) == 1  # not asked again during the cooldown
    clock.now = 600
    assert failsafe.generate("rules", [], []).text == "gemini is back"


def test_when_both_fail_the_error_names_both():
    primary = make_named_llm("gemini", [LLMError("quota")])
    backup = make_named_llm("groq", [LLMError("bad key")])
    with pytest.raises(LLMError) as raised:
        FallbackProvider(primary, backup).generate("rules", [], [])
    assert "gemini: quota" in str(raised.value) and "groq: bad key" in str(raised.value)


# ---- choosing providers from settings ----

def test_both_keys_make_a_failsafe_pair_in_the_chosen_order():
    llm = build_llm(Settings(_env_file=None, gemini_api_key="g", groq_api_key="q"))
    assert isinstance(llm, FallbackProvider)
    assert isinstance(llm.primary, GeminiProvider) and isinstance(llm.backup, GroqProvider)
    reversed_llm = build_llm(Settings(_env_file=None, gemini_api_key="g", groq_api_key="q", llm_provider="groq"))
    assert isinstance(reversed_llm.primary, GroqProvider) and isinstance(reversed_llm.backup, GeminiProvider)


def test_one_key_means_that_provider_alone():
    assert isinstance(build_llm(Settings(_env_file=None, gemini_api_key="g")), GeminiProvider)
    assert isinstance(build_llm(Settings(_env_file=None, groq_api_key="q", llm_provider="groq")), GroqProvider)


def test_missing_key_for_the_chosen_provider_or_unknown_provider_is_an_error():
    with pytest.raises(LLMError):
        build_llm(Settings(_env_file=None, groq_api_key="q"))  # LLM_PROVIDER is gemini, but no Gemini key
    with pytest.raises(ValueError):
        build_llm(Settings(_env_file=None, gemini_api_key="g", llm_provider="openai"))
