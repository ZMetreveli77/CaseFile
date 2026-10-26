"""LLM providers behind one interface. Provider-specific errors are translated into the two exceptions below,
so the rest of the code (retries, the agent) never depends on one vendor's SDK."""
from dataclasses import dataclass, field
from typing import Any, Callable, Protocol

RETRYABLE_STATUS_CODES = frozenset({429, 500, 502, 503, 504})  # rate limit, server error, overloaded, timeout
MILLISECONDS_PER_SECOND = 1000


class LLMError(Exception):
    """Permanent failure: retrying won't help (bad request, bad API key, unknown model, retries exhausted)."""


class RetryableLLMError(LLMError):
    """Temporary failure: worth retrying after a wait (rate limit 429, overloaded 503, server error 500, timeout)."""

    def __init__(self, message: str, retry_after_seconds: float | None = None):
        super().__init__(message)
        self.retry_after_seconds = retry_after_seconds  # set when the provider says how long to wait


# ---- Provider-neutral conversation types (the agent only uses these) ----

@dataclass
class ToolSpec:
    name: str
    description: str
    parameters: dict  # JSON schema of the arguments


@dataclass
class ToolCall:
    name: str
    arguments: dict


@dataclass
class LLMReply:
    text: str
    tool_calls: list[ToolCall] = field(default_factory=list)
    provider_content: Any = None  # the provider's original reply object, sent back unchanged on the next turn


@dataclass
class Message:
    role: str  # "user" | "assistant" | "tool"
    text: str = ""
    tool_calls: list[ToolCall] = field(default_factory=list)  # assistant turns
    tool_name: str = ""  # tool turns
    tool_result: dict | None = None  # tool turns
    provider_content: Any = None  # assistant turns: see LLMReply.provider_content

    @classmethod
    def from_reply(cls, reply: LLMReply) -> "Message":
        return cls(role="assistant", text=reply.text, tool_calls=reply.tool_calls,
                   provider_content=reply.provider_content)


class LLMProvider(Protocol):
    model_name: str

    def generate(self, system_prompt: str, messages: list[Message], tools: list[ToolSpec]) -> LLMReply: ...


# ---- Gemini ----

def translate_gemini_error(error: Exception) -> LLMError:
    """Map a google-genai / network error to RetryableLLMError (temporary) or LLMError (permanent)."""
    from google.genai import errors as gemini_errors
    import httpx

    if isinstance(error, gemini_errors.APIError):
        message = f"Gemini error {error.code}: {error.message}"
        if error.code in RETRYABLE_STATUS_CODES:
            return RetryableLLMError(message)
        return LLMError(message)
    if isinstance(error, (httpx.TimeoutException, httpx.NetworkError)):
        return RetryableLLMError(f"Network problem talking to Gemini: {error}")
    return LLMError(f"Unexpected Gemini failure: {error}")


class GeminiProvider:
    def __init__(self, api_key: str, model_name: str, timeout_seconds: int,
                 call_with_retries: Callable | None = None):
        if not api_key:
            raise LLMError("GEMINI_API_KEY is not set (add it to .env)")
        from google import genai
        from google.genai import types

        self.types = types
        self.model_name = model_name
        self.client = genai.Client(api_key=api_key,
                                   http_options=types.HttpOptions(timeout=timeout_seconds * MILLISECONDS_PER_SECOND))
        self.call_with_retries = call_with_retries

    def generate(self, system_prompt: str, messages: list[Message], tools: list[ToolSpec]) -> LLMReply:
        config = self.types.GenerateContentConfig(
            system_instruction=system_prompt,
            temperature=0,  # same question -> same reasoning, as far as the model allows (helps evaluation)
            tools=[self.convert_tools(tools)] if tools else None,
            # We run the tool loop ourselves (agent.py), so the SDK must not call Python functions on its own.
            automatic_function_calling=self.types.AutomaticFunctionCallingConfig(disable=True),
        )
        contents = [self.convert_message(message) for message in messages]

        def send_request():
            try:
                return self.client.models.generate_content(model=self.model_name, contents=contents, config=config)
            except Exception as error:
                raise translate_gemini_error(error) from error

        call_with_retries = self.call_with_retries
        if call_with_retries is None:
            from casefile.rag.retry import call_with_retries  # written as task U6
        response = call_with_retries(send_request)
        return self.convert_response(response)

    def convert_tools(self, tools: list[ToolSpec]):
        return self.types.Tool(function_declarations=[
            self.types.FunctionDeclaration(name=tool.name, description=tool.description, parameters=tool.parameters)
            for tool in tools])

    def convert_message(self, message: Message):
        types = self.types
        if message.role == "assistant":
            if message.provider_content is not None:
                return message.provider_content  # keeps Gemini's hidden "thought signatures" on tool calls
            parts = [types.Part(text=message.text)] if message.text else []
            parts += [types.Part(function_call=types.FunctionCall(name=call.name, args=call.arguments))
                      for call in message.tool_calls]
            return types.Content(role="model", parts=parts)
        if message.role == "tool":
            return types.Content(role="user", parts=[
                types.Part.from_function_response(name=message.tool_name, response=message.tool_result or {})])
        return types.Content(role="user", parts=[types.Part(text=message.text)])

    def export_content(self, content) -> str:
        """Gemini reply object -> JSON text, for the evaluation cache (keeps the hidden thought signatures)."""
        return content.model_dump_json(exclude_none=True)

    def restore_content(self, exported: str):
        return self.types.Content.model_validate_json(exported)

    def convert_response(self, response) -> LLMReply:
        candidates = response.candidates or []
        if not candidates or candidates[0].content is None:
            reason = candidates[0].finish_reason if candidates else "no candidates"
            raise LLMError(f"Gemini returned no content (finish reason: {reason})")
        content = candidates[0].content
        parts = content.parts or []
        text = "".join(part.text for part in parts if part.text and not part.thought)
        tool_calls = [ToolCall(name=part.function_call.name, arguments=dict(part.function_call.args or {}))
                      for part in parts if part.function_call]
        return LLMReply(text=text, tool_calls=tool_calls, provider_content=content)
