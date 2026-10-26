import json

from casefile.api.streaming import format_sse


def test_format_sse_has_event_name_data_and_ends_with_a_blank_line():
    event = {"type": "tool_call", "tool": "search_documents", "arguments": {"query": "CHG-42"}}
    message = format_sse(event)
    assert message == ('event: tool_call\n'
                       'data: {"type": "tool_call", "tool": "search_documents", "arguments": {"query": "CHG-42"}}\n\n')
    assert message.endswith("\n\n")


def test_data_stays_on_one_line_even_if_a_value_contains_newlines():
    event = {"type": "tool_result", "tool": "read_document", "titles": ["Line one\nLine two"], "error": None}
    message = format_sse(event)
    event_line, data_line, *rest = message.split("\n")
    assert event_line == "event: tool_result"
    assert data_line.startswith("data: ")
    assert rest == ["", ""]  # nothing after the data line except the blank line that ends the event
    assert json.loads(data_line.removeprefix("data: ")) == event  # the newline survives, escaped as \n