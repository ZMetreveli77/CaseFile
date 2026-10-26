"""Server-Sent Events (SSE): the format the browser's EventSource understands for a live progress stream.

One event on the wire:
    event: tool_call
    data: {"type": "tool_call", "tool": "search_documents", ...}
    <blank line>
The blank line ends the event. Each `data:` line must be a single line, which json.dumps guarantees:
a newline inside a string becomes the two characters \\n, never a real line break.
"""
import json

# A line starting with ":" is an SSE comment: clients ignore it, but the bytes keep an idle connection open.
KEEP_ALIVE_COMMENT = ": keep-alive\n\n"


def format_sse(event: dict) -> str:
    """Turn one progress event into an SSE message; the event's "type" becomes the SSE event name."""
    return f"event: {event['type']}\ndata: {json.dumps(event)}\n\n"