import httpx
import pytest
from google.genai import errors as gemini_errors
from google.genai import types

from casefile.rag.llm import (GeminiProvider, LLMError, LLMReply, Message, RetryableLLMError, ToolCall, ToolSpec,
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
