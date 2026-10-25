"""Test doubles shared by several test files."""


class FakeLLM:
    """Replays scripted replies in order and records every request, so tests need no network and no API key."""

    model_name = "fake"

    def __init__(self, replies):
        self.replies = list(replies)
        self.requests = []  # (messages, tool names) per call

    def generate(self, system_prompt, messages, tools):
        self.requests.append((list(messages), [tool.name for tool in tools]))
        reply = self.replies.pop(0)
        if isinstance(reply, Exception):
            raise reply
        return reply
