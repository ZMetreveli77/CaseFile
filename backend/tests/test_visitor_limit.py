from starlette.requests import Request

from casefile.api.visitor_limit import (MAX_TRACKED_VISITORS, SECONDS_PER_HOUR, QuestionLimiter,
                                        describe_limit_reached, identify_visitor)


class FakeClock:
    def __init__(self):
        self.now = 0.0

    def __call__(self):
        return self.now


def test_visitor_is_refused_after_the_limit_until_the_oldest_question_is_an_hour_old():
    clock = FakeClock()
    limiter = QuestionLimiter(questions_per_hour=2, clock=clock)
    assert limiter.admit_question("1.2.3.4") is None
    clock.now = 600
    assert limiter.admit_question("1.2.3.4") is None
    clock.now = 900
    assert limiter.admit_question("1.2.3.4") == SECONDS_PER_HOUR - 900  # the first question still counts
    assert limiter.admit_question("5.6.7.8") is None  # another visitor has their own allowance
    clock.now = SECONDS_PER_HOUR
    assert limiter.admit_question("1.2.3.4") is None  # the first question is an hour old now


def test_a_refused_question_does_not_count_and_zero_means_no_limit():
    limiter = QuestionLimiter(questions_per_hour=1, clock=FakeClock())
    limiter.admit_question("visitor")
    for _ in range(5):
        limiter.admit_question("visitor")
    assert len(limiter.question_times_by_visitor["visitor"]) == 1
    unlimited = QuestionLimiter(questions_per_hour=0)
    assert all(unlimited.admit_question("visitor") is None for _ in range(100))


def test_inactive_visitors_are_forgotten_when_many_are_tracked():
    clock = FakeClock()
    limiter = QuestionLimiter(questions_per_hour=5, clock=clock)
    for number in range(MAX_TRACKED_VISITORS + 1):
        limiter.admit_question(f"visitor-{number}")
    clock.now = SECONDS_PER_HOUR
    limiter.admit_question("new visitor")
    assert list(limiter.question_times_by_visitor) == ["new visitor"]


def make_request(forwarded_for=None, client_host="10.0.0.1"):
    headers = [(b"x-forwarded-for", forwarded_for.encode())] if forwarded_for else []
    return Request({"type": "http", "headers": headers, "client": (client_host, 1234)})


def test_the_visitor_is_the_address_the_proxy_added_last():
    assert identify_visitor(make_request("203.0.113.9")) == "203.0.113.9"
    # A visitor can send their own X-Forwarded-For; the proxy appends the real address, which is what counts.
    assert identify_visitor(make_request("1.1.1.1, 203.0.113.9")) == "203.0.113.9"
    assert identify_visitor(make_request()) == "10.0.0.1"  # no proxy (local run)


def test_limit_message_is_plain_and_rounds_up_to_minutes():
    message = describe_limit_reached(10, 61)
    assert "10 questions" in message and "2 minutes" in message
    assert "1 minute." in describe_limit_reached(10, 5)
    assert "429" not in message and "quota" not in message.lower()  # the UI would rewrite those
