import httpx
import pytest
from google.genai import errors as gemini_errors
from google.genai import types

from casefile.rag.llm import (MAX_RETRY_AFTER_SECONDS, GeminiProvider, LLMError, LLMReply, Message, RequestRateLimiter,
                              RetryableLLMError, ToolCall, ToolSpec,
                              translate_gemini_error)


def gemini_api_error(code):
    return gemini_errors.APIError(code, {"error": {"code": code, "message": f"status {code}", "status": "X"}})


@pytest.mark.parametrize("code", [429, 500, 502, 503, 504])
def test_temporary_gemini_errors_are_retryable(code):
    assert isinstance(translate_gemini_error(gemini_api_error(code)), RetryableLLMError)


@pytest.mark.parametrize("code", [400, 401, 403, 404])
def test_permanent_gemini_errors_are_not_retryable(code):
    translated = translate_gemini_error(gemini_api_error(code))
    assert isinstance(translated, LLMError) and not isinstance(translated, RetryableLLMError)


def test_network_timeout_is_retryable():
    assert isinstance(translate_gemini_error(httpx.ReadTimeout("slow")), RetryableLLMError)


def test_missing_api_key_fails_fast():
    with pytest.raises(LLMError):
        GeminiProvider(api_key="", model_name="any", timeout_seconds=1)


@pytest.fixture
def provider():
    return GeminiProvider(api_key="test-key", model_name="test-model", timeout_seconds=1,
                          call_with_retries=lambda action: action())


def test_messages_are_converted_to_gemini_roles(provider):
    user = provider.convert_message(Message(role="user", text="hi"))
    tool = provider.convert_message(Message(role="tool", tool_name="search_documents", tool_result={"results": []}))
    assistant = provider.convert_message(Message(role="assistant",
                                                 tool_calls=[ToolCall("search_documents", {"query": "q"})]))
    assert (user.role, tool.role, assistant.role) == ("user", "user", "model")
    assert tool.parts[0].function_response.name == "search_documents"
    assert assistant.parts[0].function_call.args == {"query": "q"}


def test_original_assistant_content_is_sent_back_unchanged(provider):
    original = types.Content(role="model", parts=[types.Part(text="kept as is")])
    message = Message.from_reply(LLMReply(text="kept as is", provider_content=original))
    assert provider.convert_message(message) is original  # preserves Gemini's thought signatures


def test_response_with_tool_call_is_converted(provider):
    response = types.GenerateContentResponse(candidates=[types.Candidate(content=types.Content(role="model", parts=[
        types.Part(text="Let me search."),
        types.Part(function_call=types.FunctionCall(name="search_documents", args={"query": "Big Stone Gap"})),
    ]))])
    reply = provider.convert_response(response)
    assert reply.text == "Let me search."
    assert reply.tool_calls == [ToolCall("search_documents", {"query": "Big Stone Gap"})]


def test_empty_response_is_a_clear_error(provider):
    with pytest.raises(LLMError):
        provider.convert_response(types.GenerateContentResponse(candidates=[]))


def test_tool_specs_become_function_declarations(provider):
    spec = ToolSpec("search_documents", "Search.", {"type": "object", "properties": {"query": {"type": "string"}}})
    assert provider.convert_tools([spec]).function_declarations[0].name == "search_documents"


def rate_limit_error(details, message):
    return gemini_errors.APIError(429, {"error": {"code": 429, "message": message, "status": "RESOURCE_EXHAUSTED",
                                                  "details": details}})


def test_rate_limit_carries_the_providers_retry_delay():
    structured = rate_limit_error([{"@type": "type.googleapis.com/google.rpc.RetryInfo", "retryDelay": "49s"}],
                                  "Quota exceeded. Please retry in 49.6s.")
    assert translate_gemini_error(structured).retry_after_seconds == 49.0  # the structured hint wins
    text_only = rate_limit_error([], "Quota exceeded. Please retry in 12.5s.")
    assert translate_gemini_error(text_only).retry_after_seconds == 12.5
    no_hint = rate_limit_error([], "Quota exceeded.")
    assert translate_gemini_error(no_hint).retry_after_seconds is None


def test_a_wait_longer_than_the_cap_fails_at_once_instead_of_retrying():
    daily_quota = rate_limit_error([{"retryDelay": "25575s"}], "Quota exceeded (per day). Please retry in 7h6m15s.")
    translated = translate_gemini_error(daily_quota)
    assert isinstance(translated, LLMError) and not isinstance(translated, RetryableLLMError)
    assert "daily quota" in str(translated)
    at_the_cap = rate_limit_error([{"retryDelay": f"{MAX_RETRY_AFTER_SECONDS:.0f}s"}], "")
    assert translate_gemini_error(at_the_cap).retry_after_seconds == MAX_RETRY_AFTER_SECONDS  # still retried


class FakeClock:
    def __init__(self):
        self.now = 0.0
        self.sleeps = []

    def time(self):
        return self.now

    def sleep(self, seconds):
        self.sleeps.append(seconds)
        self.now += seconds


def test_rate_limiter_waits_only_when_the_minute_is_full():
    clock = FakeClock()
    limiter = RequestRateLimiter(requests_per_minute=3, clock=clock.time, sleep=clock.sleep)
    for _ in range(3):
        limiter.wait_for_turn()
        clock.now += 1  # one request per second
    assert clock.sleeps == []  # 3 requests in 3 s: within the limit
    limiter.wait_for_turn()  # the 4th inside the same minute must wait until the 1st is a minute old
    assert clock.sleeps == [pytest.approx(57.0)]


def test_rate_limiter_does_not_wait_after_the_window_passed_and_zero_means_unlimited():
    clock = FakeClock()
    limiter = RequestRateLimiter(requests_per_minute=2, clock=clock.time, sleep=clock.sleep)
    limiter.wait_for_turn()
    limiter.wait_for_turn()
    clock.now += 61
    limiter.wait_for_turn()
    assert clock.sleeps == []
    unlimited = RequestRateLimiter(requests_per_minute=0, clock=clock.time, sleep=clock.sleep)
    for _ in range(100):
        unlimited.wait_for_turn()
    assert clock.sleeps == []
