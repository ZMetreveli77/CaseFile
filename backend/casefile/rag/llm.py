"""LLM providers behind one interface. Provider-specific errors are translated into the two exceptions below,
so the rest of the code (retries, the agent) never depends on one vendor's SDK.

Gemini is the main provider; Groq is the failsafe (FallbackProvider switches to it when Gemini fails)."""
import json
import re
import threading
import time
from collections import deque
from dataclasses import dataclass, field
from typing import Any, Callable, Protocol

import httpx

RETRYABLE_STATUS_CODES = frozenset({429, 500, 502, 503, 504})  # rate limit, server error, overloaded, timeout
MILLISECONDS_PER_SECOND = 1000
MAX_RETRY_AFTER_SECONDS = 120.0  # never trust a provider's "wait this long" hint beyond this (keeps the app responsive)
RETRY_DELAY_IN_MESSAGE = re.compile(r"retry in ([\d.]+)\s*s", re.IGNORECASE)  # "Please retry in 49.6s."
SECONDS_PER_MINUTE = 60.0
GROQ_CHAT_URL = "https://api.groq.com/openai/v1/chat/completions"  # OpenAI-compatible endpoint
# Groq's 400 code when the model's tool call was malformed, e.g. gpt-oss sending its final JSON answer as a call to a
# tool named "json". A generation problem, not a bad request, so it is retried.
GROQ_BAD_TOOL_CALL_CODE = "tool_use_failed"
PRIMARY_COOLDOWN_SECONDS = 600.0  # after the main provider fails, use the backup for this long before trying it again
MAX_ERROR_CHARACTERS_IN_NOTE = 160  # provider errors can be long; the answer note keeps the start


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
    fallback_reason: str = ""  # set by FallbackProvider when the backup model wrote this reply


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

def find_retry_delay_seconds(error_json: Any, message: str) -> float | None:
    """How long the provider asked us to wait, e.g. after a 429 rate limit; None if it didn't say.

    Google's errors carry a structured hint ({"@type": ".../google.rpc.RetryInfo", "retryDelay": "49s"}) and repeat it
    in the text ("Please retry in 49.6s."). The structured one is read first. Not capped here: the caller decides
    what a very long wait means (see translate_gemini_error).
    """
    details = (error_json or {}).get("error", {}).get("details", []) if isinstance(error_json, dict) else []
    for detail in details if isinstance(details, list) else []:
        delay = detail.get("retryDelay") if isinstance(detail, dict) else None
        if isinstance(delay, str) and delay.endswith("s"):
            try:
                return float(delay[:-1])
            except ValueError:
                pass
    match = RETRY_DELAY_IN_MESSAGE.search(message)
    return float(match.group(1)) if match else None


class RequestRateLimiter:
    """Keeps requests under a per-minute limit (Gemini's free tier allows 15/min), waiting when a send would exceed it.

    Sliding window: remember when the recent requests were sent; if the window is full, sleep until the oldest one is
    a minute old. Prevents most 429 errors instead of recovering from them. Thread-safe (the API serves in parallel).
    """

    def __init__(self, requests_per_minute: int, clock: Callable[[], float] = time.monotonic,
                 sleep: Callable[[float], None] = time.sleep):
        self.requests_per_minute = requests_per_minute
        self.clock, self.sleep = clock, sleep
        self.sent_times: deque[float] = deque()
        self.lock = threading.Lock()

    def wait_for_turn(self) -> None:
        if self.requests_per_minute <= 0:  # 0 = no limit
            return
        with self.lock:
            now = self.clock()
            while self.sent_times and now - self.sent_times[0] >= SECONDS_PER_MINUTE:
                self.sent_times.popleft()  # older than a minute: no longer counts
            if len(self.sent_times) >= self.requests_per_minute:
                self.sleep(SECONDS_PER_MINUTE - (now - self.sent_times[0]))
                self.sent_times.popleft()
                now = self.clock()
            self.sent_times.append(now)


def translate_gemini_error(error: Exception) -> LLMError:
    """Map a google-genai / network error to RetryableLLMError (temporary) or LLMError (permanent)."""
    from google.genai import errors as gemini_errors
    import httpx

    if isinstance(error, gemini_errors.APIError):
        message = f"Gemini error {error.code}: {error.message}"
        if error.code in RETRYABLE_STATUS_CODES:
            retry_after_seconds = find_retry_delay_seconds(error.details, message)
            # A wait longer than MAX_RETRY_AFTER_SECONDS (e.g. a daily quota: "retry in 7h") can't be bridged by
            # retrying, so fail at once with a clear error instead of retrying for minutes and then failing anyway.
            if retry_after_seconds is not None and retry_after_seconds > MAX_RETRY_AFTER_SECONDS:
                return LLMError(f"{message} (the provider asks to wait {retry_after_seconds / 3600:.1f} h, "
                                "probably a daily quota; not retrying)")
            return RetryableLLMError(message, retry_after_seconds=retry_after_seconds)
        return LLMError(message)
    if isinstance(error, (httpx.TimeoutException, httpx.NetworkError)):
        return RetryableLLMError(f"Network problem talking to Gemini: {error}")
    return LLMError(f"Unexpected Gemini failure: {error}")


class GeminiProvider:
    def __init__(self, api_key: str, model_name: str, timeout_seconds: int,
                 call_with_retries: Callable | None = None, requests_per_minute: int = 0):
        if not api_key:
            raise LLMError("GEMINI_API_KEY is not set (add it to .env)")
        from google import genai
        from google.genai import types

        self.types = types
        self.model_name = model_name
        self.client = genai.Client(api_key=api_key,
                                   http_options=types.HttpOptions(timeout=timeout_seconds * MILLISECONDS_PER_SECOND))
        self.call_with_retries = call_with_retries
        self.rate_limiter = RequestRateLimiter(requests_per_minute)

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
            self.rate_limiter.wait_for_turn()  # inside the retried function, so retries are paced too
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


# ---- Groq (the failsafe) ----

def convert_messages_to_openai_format(system_prompt: str, messages: list[Message]) -> list[dict]:
    """Our neutral messages -> the OpenAI chat format that Groq uses.

    Works for a conversation that another provider started (the failsafe can take over in the middle of an
    investigation), so it only uses the neutral fields and ignores provider_content (e.g. Gemini's reply objects).

    OpenAI's format links every tool result to its tool call by an id; our messages have no ids. The agent always adds
    tool results in the same order as the calls, so ids are given out in order (call_0, call_1, ...) and each tool
    result takes the oldest id that hasn't been answered yet (first in, first out).
    """
    converted = [{"role": "system", "content": system_prompt}]
    unanswered_call_ids: deque[str] = deque()
    call_count = 0
    for message in messages:
        if message.role == "assistant":
            if not message.text and not message.tool_calls:
                continue  # an empty assistant turn: the API rejects a message with no content
            assistant_message: dict = {"role": "assistant", "content": message.text or None}
            if message.tool_calls:
                assistant_message["tool_calls"] = []
                for tool_call in message.tool_calls:
                    call_id = f"call_{call_count}"
                    call_count += 1
                    unanswered_call_ids.append(call_id)
                    assistant_message["tool_calls"].append({
                        "id": call_id, "type": "function",
                        "function": {"name": tool_call.name,
                                     "arguments": json.dumps(tool_call.arguments, ensure_ascii=False)}})
            converted.append(assistant_message)
        elif message.role == "tool":
            if not unanswered_call_ids:
                raise LLMError(f"Tool result for '{message.tool_name}' without a matching tool call")
            converted.append({"role": "tool", "tool_call_id": unanswered_call_ids.popleft(),
                              "content": json.dumps(message.tool_result or {}, ensure_ascii=False)})
        else:
            converted.append({"role": "user", "content": message.text})
    return converted


def translate_groq_error(status_code: int, response_text: str, retry_after_header: str | None) -> LLMError:
    """Map a Groq HTTP error to RetryableLLMError (temporary) or LLMError (permanent), the same rules as Gemini."""
    try:
        error_json = json.loads(response_text).get("error", {})
        detail, error_code = error_json.get("message", response_text), error_json.get("code")
    except (ValueError, AttributeError):
        detail, error_code = response_text, None
    message = f"Groq error {status_code}: {detail}"
    if error_code == GROQ_BAD_TOOL_CALL_CODE:
        return RetryableLLMError(message)  # the model wrote a malformed tool call; a new attempt usually works
    if status_code not in RETRYABLE_STATUS_CODES:
        return LLMError(message)  # e.g. 401 bad key, 400 malformed tool call, 413 request too large
    try:
        retry_after_seconds = float(retry_after_header) if retry_after_header else None  # Groq sends seconds
    except ValueError:
        retry_after_seconds = None
    if retry_after_seconds is not None and retry_after_seconds > MAX_RETRY_AFTER_SECONDS:
        return LLMError(f"{message} (the provider asks to wait {retry_after_seconds / 3600:.1f} h, "
                        "probably a daily quota; not retrying)")
    return RetryableLLMError(message, retry_after_seconds=retry_after_seconds)


class GroqProvider:
    """Groq's chat API over plain HTTP (httpx), so no extra SDK. Free tier for openai/gpt-oss-120b (Oct 2026):
    30 requests/min, 1,000 requests/day, 8,000 tokens/min. Hitting the token limit gives a 429 with a short
    retry-after, which call_with_retries waits out."""

    def __init__(self, api_key: str, model_name: str, timeout_seconds: int,
                 call_with_retries: Callable | None = None, requests_per_minute: int = 0,
                 http_client: httpx.Client | None = None):
        if not api_key:
            raise LLMError("GROQ_API_KEY is not set (add it to .env)")
        self.model_name = model_name
        self.headers = {"Authorization": f"Bearer {api_key}"}
        self.http_client = http_client or httpx.Client(timeout=timeout_seconds)  # tests pass a fake transport
        self.call_with_retries = call_with_retries
        self.rate_limiter = RequestRateLimiter(requests_per_minute)

    def generate(self, system_prompt: str, messages: list[Message], tools: list[ToolSpec]) -> LLMReply:
        request_body: dict = {"model": self.model_name, "temperature": 0,
                              "messages": convert_messages_to_openai_format(system_prompt, messages)}
        if tools:
            request_body["tools"] = self.convert_tools(tools)

        def send_request() -> dict:
            self.rate_limiter.wait_for_turn()
            try:
                response = self.http_client.post(GROQ_CHAT_URL, headers=self.headers, json=request_body)
            except (httpx.TimeoutException, httpx.NetworkError) as error:
                raise RetryableLLMError(f"Network problem talking to Groq: {error}") from error
            except httpx.HTTPError as error:
                raise LLMError(f"Unexpected Groq failure: {error}") from error
            if response.status_code != 200:
                raise translate_groq_error(response.status_code, response.text, response.headers.get("retry-after"))
            return response.json()

        call_with_retries = self.call_with_retries
        if call_with_retries is None:
            from casefile.rag.retry import call_with_retries
        return self.convert_response(call_with_retries(send_request))

    def convert_tools(self, tools: list[ToolSpec]) -> list[dict]:
        return [{"type": "function", "function": {"name": tool.name, "description": tool.description,
                                                  "parameters": tool.parameters}} for tool in tools]

    def convert_response(self, response_json: dict) -> LLMReply:
        choices = response_json.get("choices") or []
        if not choices:
            raise LLMError("Groq returned no choices")
        reply_message = choices[0].get("message") or {}
        tool_calls = []
        for tool_call in reply_message.get("tool_calls") or []:
            function = tool_call.get("function") or {}
            try:
                arguments = json.loads(function.get("arguments") or "{}")  # OpenAI sends arguments as a JSON string
            except ValueError as error:
                raise LLMError(f"Groq returned invalid tool arguments: {function.get('arguments')!r}") from error
            tool_calls.append(ToolCall(name=function.get("name", ""),
                                       arguments=arguments if isinstance(arguments, dict) else {}))
        return LLMReply(text=reply_message.get("content") or "", tool_calls=tool_calls)


# ---- Failsafe ----

class FallbackProvider:
    """Asks the primary provider; if it fails (an LLMError, so after its own retries), the backup answers instead.

    A simple circuit breaker: after a primary failure, the primary is skipped for `cooldown_seconds`. A daily quota or
    an outage won't be over in a few seconds, and trying the primary first on every call would add its retries to
    every answer (and switch providers back and forth inside one investigation).
    Every reply from the backup carries a fallback_reason, which the agent shows as a note on the answer.
    """

    def __init__(self, primary: LLMProvider, backup: LLMProvider, cooldown_seconds: float = PRIMARY_COOLDOWN_SECONDS,
                 clock: Callable[[], float] = time.monotonic):
        self.primary, self.backup = primary, backup
        self.model_name = primary.model_name
        self.backup_model_name = backup.model_name
        self.cooldown_seconds = cooldown_seconds
        self.clock = clock
        self.primary_skipped_until = float("-inf")  # clock time until which the primary is not tried
        self.last_primary_error = ""
        self.lock = threading.Lock()  # the API answers several questions in parallel

    def is_primary_cooling_down(self) -> bool:
        return self.clock() < self.primary_skipped_until

    def generate(self, system_prompt: str, messages: list[Message], tools: list[ToolSpec]) -> LLMReply:
        if not self.is_primary_cooling_down():
            try:
                return self.primary.generate(system_prompt, messages, tools)
            except LLMError as error:
                with self.lock:
                    self.primary_skipped_until = self.clock() + self.cooldown_seconds
                    self.last_primary_error = str(error)
        try:
            reply = self.backup.generate(system_prompt, messages, tools)
        except LLMError as backup_error:
            raise LLMError(f"Both language models failed. {self.primary.model_name}: {self.last_primary_error} | "
                           f"{self.backup.model_name}: {backup_error}") from backup_error
        reply.fallback_reason = (f"{self.primary.model_name} was unavailable "
                                 f"({self.last_primary_error[:MAX_ERROR_CHARACTERS_IN_NOTE]}); "
                                 f"answered by the backup model {self.backup.model_name}")
        return reply
