"""Disk cache for LLM calls, so re-running an evaluation replays saved replies instead of spending the free-tier quota.

The key is a hash of EVERYTHING sent: model, system prompt, tool names, and every message (including tool results).
If anything changes (a prompt, a retrieval setting, a different search result), the key changes and the call is real,
so a stale reply can never be served for a different request.
"""
import hashlib
import json
from pathlib import Path

from casefile.rag.llm import LLMProvider, LLMReply, Message, ToolCall, ToolSpec


def describe_message(message: Message) -> dict:
    return {"role": message.role, "text": message.text, "tool_name": message.tool_name,
            "tool_result": message.tool_result,
            "tool_calls": [[tool_call.name, tool_call.arguments] for tool_call in message.tool_calls]}


class CachingLLM:
    """Wraps any LLMProvider; same generate() method, so the agent can't tell the difference."""

    def __init__(self, provider: LLMProvider, cache_folder: Path):
        self.provider = provider
        self.model_name = provider.model_name
        self.cache_folder = Path(cache_folder)
        self.cache_folder.mkdir(parents=True, exist_ok=True)
        self.hits = 0  # replies replayed from disk
        self.misses = 0  # real LLM calls

    def build_key(self, system_prompt: str, messages: list[Message], tools: list[ToolSpec]) -> str:
        request = {"model": self.model_name, "system_prompt": system_prompt, "tools": [tool.name for tool in tools],
                   "messages": [describe_message(message) for message in messages]}
        encoded = json.dumps(request, sort_keys=True, ensure_ascii=False, default=str).encode("utf-8")
        return hashlib.sha256(encoded).hexdigest()

    def generate(self, system_prompt: str, messages: list[Message], tools: list[ToolSpec]) -> LLMReply:
        cache_file = self.cache_folder / f"{self.build_key(system_prompt, messages, tools)}.json"
        if cache_file.exists():
            self.hits += 1
            return self.restore_reply(json.loads(cache_file.read_text(encoding="utf-8")))
        reply = self.provider.generate(system_prompt, messages, tools)
        self.misses += 1
        cache_file.write_text(json.dumps(self.export_reply(reply), ensure_ascii=False), encoding="utf-8")
        return reply

    def export_reply(self, reply: LLMReply) -> dict:
        export_content = getattr(self.provider, "export_content", None)
        provider_content = export_content(reply.provider_content) if export_content and reply.provider_content else None
        return {"text": reply.text, "provider_content": provider_content,
                "tool_calls": [{"name": tool_call.name, "arguments": tool_call.arguments} for tool_call in reply.tool_calls]}

    def restore_reply(self, saved: dict) -> LLMReply:
        restore_content = getattr(self.provider, "restore_content", None)
        provider_content = restore_content(saved["provider_content"]) if restore_content and saved["provider_content"] else None
        return LLMReply(text=saved["text"], provider_content=provider_content,
                        tool_calls=[ToolCall(item["name"], item["arguments"]) for item in saved["tool_calls"]])
