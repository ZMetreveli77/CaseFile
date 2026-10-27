"""Per-visitor question limit for the public demo, so one visitor can't use up the shared free LLM quota
(Gemini's free tier allows ~500 requests/day, and one question costs about 3)."""
import math
import threading
import time
from collections import deque
from typing import Callable

from fastapi import Request

SECONDS_PER_HOUR = 3600.0
SECONDS_PER_MINUTE = 60
MAX_TRACKED_VISITORS = 1000  # above this, visitors with no question in the last hour are forgotten (bounded memory)


def identify_visitor(request: Request) -> str:
    """The visitor's IP address.

    Behind Render's proxy, request.client is the proxy, not the visitor. The proxy APPENDS the address it received the
    request from to X-Forwarded-For, so the LAST entry is the one we can trust; earlier entries come from the visitor
    and could be made up to dodge the limit.
    """
    forwarded_for = [host.strip() for host in request.headers.get("x-forwarded-for", "").split(",") if host.strip()]
    if forwarded_for:
        return forwarded_for[-1]
    return request.client.host if request.client else "unknown"


class QuestionLimiter:
    """At most `questions_per_hour` questions per visitor in any rolling hour.

    Sliding window, like RequestRateLimiter in rag/llm.py, but it refuses instead of waiting: a visitor shouldn't wait
    up to an hour for a reply. Thread-safe, because the API answers several requests at once.
    """

    def __init__(self, questions_per_hour: int, clock: Callable[[], float] = time.monotonic):
        self.questions_per_hour = questions_per_hour
        self.clock = clock
        self.question_times_by_visitor: dict[str, deque[float]] = {}
        self.lock = threading.Lock()

    def admit_question(self, visitor_id: str) -> float | None:
        """Count the question and return None if the visitor is under the limit; otherwise count nothing and return
        the seconds until they may ask again."""
        if self.questions_per_hour <= 0:  # 0 = no limit
            return None
        with self.lock:
            now = self.clock()
            if len(self.question_times_by_visitor) > MAX_TRACKED_VISITORS:
                self.forget_inactive_visitors(now)
            question_times = self.question_times_by_visitor.setdefault(visitor_id, deque())
            while question_times and now - question_times[0] >= SECONDS_PER_HOUR:
                question_times.popleft()  # older than an hour: no longer counts
            if len(question_times) >= self.questions_per_hour:
                return SECONDS_PER_HOUR - (now - question_times[0])
            question_times.append(now)
            return None

    def forget_inactive_visitors(self, now: float) -> None:
        self.question_times_by_visitor = {
            visitor_id: question_times for visitor_id, question_times in self.question_times_by_visitor.items()
            if question_times and now - question_times[-1] < SECONDS_PER_HOUR}


def describe_limit_reached(questions_per_hour: int, wait_seconds: float) -> str:
    """Shown in the UI as is, so plain words (the UI rewrites messages that mention a provider quota)."""
    minutes = max(1, math.ceil(wait_seconds / SECONDS_PER_MINUTE))
    return (f"This public demo allows {questions_per_hour} questions per visitor per hour. "
            f"You can ask again in {minutes} minute{'s' if minutes != 1 else ''}.")
