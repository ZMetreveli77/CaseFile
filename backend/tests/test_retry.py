import pytest

from casefile.rag.llm import LLMError, RetryableLLMError
from casefile.rag.retry import JITTER_FRACTION, call_with_retries

NO_JITTER = lambda: 0.0  # noqa: E731  (random fraction 0 -> waits are exactly base * 2^retry)
FULL_JITTER = lambda: 1.0  # noqa: E731  (random fraction 1 -> the largest possible jitter)


class ScriptedAction:
    """Fake LLM call: each call takes the next outcome; an exception is raised, anything else is returned."""

    def __init__(self, *outcomes):
        self.remaining_outcomes = list(outcomes)
        self.call_count = 0

    def __call__(self):
        self.call_count += 1
        outcome = self.remaining_outcomes.pop(0)
        if isinstance(outcome, Exception):
            raise outcome
        return outcome


def test_succeeds_on_the_first_try_without_sleeping():
    recorded_waits = []
    action = ScriptedAction("answer")
    assert call_with_retries(action, sleep=recorded_waits.append) == "answer"
    assert action.call_count == 1
    assert recorded_waits == []


def test_succeeds_after_two_temporary_failures():
    recorded_waits = []
    action = ScriptedAction(RetryableLLMError("429"), RetryableLLMError("503"), "answer")
    result = call_with_retries(action, sleep=recorded_waits.append, draw_random_fraction=NO_JITTER)
    assert result == "answer"
    assert recorded_waits == [1.0, 2.0]


@pytest.mark.parametrize("permanent_error", [LLMError("400 bad request"), ValueError("bug in our code")])
def test_permanent_error_is_raised_immediately(permanent_error):
    recorded_waits = []
    action = ScriptedAction(permanent_error, "never reached")
    with pytest.raises(type(permanent_error)) as raised:
        call_with_retries(action, sleep=recorded_waits.append)
    assert raised.value is permanent_error  # the original error, not wrapped
    assert action.call_count == 1
    assert recorded_waits == []


def test_gives_up_after_max_attempts_and_keeps_the_last_error():
    recorded_waits = []
    last_error = RetryableLLMError("503 overloaded, third time")
    action = ScriptedAction(RetryableLLMError("429"), RetryableLLMError("503"), last_error)
    with pytest.raises(LLMError) as raised:
        call_with_retries(action, max_attempts=3, sleep=recorded_waits.append)
    # RetryableLLMError is a subclass of LLMError, so check the exact type: the caller must see a permanent error.
    assert type(raised.value) is LLMError
    assert "3 attempts" in str(raised.value)
    assert raised.value.__cause__ is last_error  # set by "raise ... from last_error"
    assert action.call_count == 3
    assert len(recorded_waits) == 2  # no wait after the final attempt


def test_waits_double_and_are_capped():
    recorded_waits = []
    action = ScriptedAction(*[RetryableLLMError("429")] * 7, "answer")
    call_with_retries(action, max_attempts=8, base_delay_seconds=1.0, max_delay_seconds=10.0,
                      sleep=recorded_waits.append, draw_random_fraction=NO_JITTER)
    assert recorded_waits == [1.0, 2.0, 4.0, 8.0, 10.0, 10.0, 10.0]


def test_jitter_adds_at_most_the_jitter_fraction_and_never_exceeds_the_cap():
    recorded_waits = []
    action = ScriptedAction(*[RetryableLLMError("429")] * 5, "answer")
    call_with_retries(action, max_attempts=6, base_delay_seconds=1.0, max_delay_seconds=10.0,
                      sleep=recorded_waits.append, draw_random_fraction=FULL_JITTER)
    assert recorded_waits == [1.0 * (1 + JITTER_FRACTION), 2.0 * (1 + JITTER_FRACTION),
                              4.0 * (1 + JITTER_FRACTION), 10.0, 10.0]


def test_real_random_jitter_stays_in_range():
    recorded_waits = []
    action = ScriptedAction(*[RetryableLLMError("429")] * 6, "answer")
    call_with_retries(action, max_attempts=7, base_delay_seconds=1.0, max_delay_seconds=10.0,
                      sleep=recorded_waits.append)  # real random.random
    for retry_number, wait_seconds in enumerate(recorded_waits, start=1):
        backoff_without_jitter = min(1.0 * 2 ** (retry_number - 1), 10.0)
        assert backoff_without_jitter <= wait_seconds <= min(backoff_without_jitter * (1 + JITTER_FRACTION), 10.0)


def test_retry_after_hint_replaces_the_computed_backoff():
    recorded_waits = []
    action = ScriptedAction(RetryableLLMError("429", retry_after_seconds=7.0), RetryableLLMError("503"), "answer")
    call_with_retries(action, sleep=recorded_waits.append, draw_random_fraction=NO_JITTER)
    assert recorded_waits == [7.0, 2.0]  # hint used once; the next wait falls back to the normal backoff