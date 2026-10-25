"""Retry temporary LLM failures (RetryableLLMError) with exponential backoff and jitter.

Exponential backoff: wait 1 s, 2 s, 4 s, 8 s ... (base * 2^retry), capped at MAX_DELAY_SECONDS, so a struggling
server gets more and more breathing room. Jitter: each wait gets a random extra of up to JITTER_FRACTION, so many
clients that failed at the same moment (e.g. 100 users hitting a 429 together) don't all retry at the same moment
and cause the next 429 together.

This module only knows our own exceptions (rag/llm.py), so it works for Gemini, Groq or any other provider.
`sleep` and `draw_random_fraction` are parameters (dependency injection), so tests never really wait.
"""
import random
import time
from typing import Callable, TypeVar

from casefile.rag.llm import LLMError, RetryableLLMError

MAX_ATTEMPTS = 5  # total calls, the first one included
BASE_DELAY_SECONDS = 1.0  # wait before the 1st retry; doubles before each further retry
MAX_DELAY_SECONDS = 30.0  # no computed wait is ever longer than this
JITTER_FRACTION = 0.5  # each wait gets a random extra of 0% to +50%

ActionResult = TypeVar("ActionResult")


def compute_backoff_seconds(retry_number: int, base_delay_seconds: float, max_delay_seconds: float,
                            random_fraction: float) -> float:
    """Wait before retry number `retry_number` (1 = first retry): base * 2^(retry-1), plus jitter, capped.

    `random_fraction` is between 0 and 1; 0 means no jitter, 1 means the full +JITTER_FRACTION.
    The cap is applied last, so the promise "never longer than max_delay_seconds" holds even with jitter.
    """
    exponential_delay = base_delay_seconds * 2 ** (retry_number - 1)
    jittered_delay = exponential_delay * (1 + JITTER_FRACTION * random_fraction)
    return min(jittered_delay, max_delay_seconds)


def call_with_retries(action: Callable[[], ActionResult], max_attempts: int = MAX_ATTEMPTS,
                      base_delay_seconds: float = BASE_DELAY_SECONDS, max_delay_seconds: float = MAX_DELAY_SECONDS,
                      sleep: Callable[[float], None] = time.sleep,
                      draw_random_fraction: Callable[[], float] = random.random) -> ActionResult:
    """Call action(); on RetryableLLMError wait and try again; return its result.

    Any other exception (including a permanent LLMError) is raised immediately, with no waiting.
    After max_attempts failed calls, raises LLMError with the number of attempts, chained to the last error.
    If the provider said how long to wait (retry_after_seconds), that wait is used instead of the backoff.
    """
    if max_attempts < 1:
        raise ValueError(f"max_attempts must be at least 1, got {max_attempts}")
    last_error: RetryableLLMError | None = None
    for attempt_number in range(1, max_attempts + 1):
        try:
            return action()
        except RetryableLLMError as error:
            last_error = error
            is_last_attempt = attempt_number == max_attempts
            if is_last_attempt:
                break  # no point waiting when no further attempt follows
            has_retry_after_hint = error.retry_after_seconds is not None
            if has_retry_after_hint:
                wait_seconds = error.retry_after_seconds  # the provider knows best when its limit resets
            else:
                wait_seconds = compute_backoff_seconds(attempt_number, base_delay_seconds, max_delay_seconds,
                                                       draw_random_fraction())
            sleep(wait_seconds)
    raise LLMError(f"Gave up after {max_attempts} attempts; last error: {last_error}") from last_error