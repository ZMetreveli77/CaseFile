"""Multi-step investigation agent: the LLM searches, reads, searches again, then answers with citations.

Loop: LLM reply -> if it asks for tools, run them and send the results back -> repeat, at most MAX_TOOL_STEPS times
-> parse the final JSON answer -> keep only citations that point at chunks the agent actually retrieved.
"""
import json
import logging
from dataclasses import dataclass, field
from typing import Callable

from casefile.rag.llm import LLMProvider, LLMReply, Message, ToolSpec
from casefile.rag.prompts import FINAL_ANSWER_REMINDER, FORMAT_REPAIR_REMINDER, build_system_prompt
from casefile.rag.tools import AGENT_TOOLS, ToolExecutor

MAX_TOOL_STEPS = 5  # rounds of tool use per question: enough for 2-hop questions, bounded cost on the free tier
INVALID_FORMAT_REASON = "The model did not return a valid answer, so no answer is given."
logger = logging.getLogger(__name__)
ProgressCallback = Callable[[dict], None]  # receives JSON-serializable progress events, e.g. for a live UI


@dataclass
class Claim:
    text: str
    citations: list[str] = field(default_factory=list)  # chunk ids


@dataclass
class Conflict:
    description: str
    citations: list[str] = field(default_factory=list)


@dataclass
class InvestigationAnswer:
    question: str
    answer: str = ""
    claims: list[Claim] = field(default_factory=list)
    conflicts: list[Conflict] = field(default_factory=list)
    should_abstain: bool = False
    abstain_reason: str = ""
    # Trace, for the UI and the evaluation:
    search_queries: list[str] = field(default_factory=list)
    retrieved_chunk_ids: list[str] = field(default_factory=list)
    source_titles: dict[str, str] = field(default_factory=dict)  # chunk_id -> document title, to show citations
    llm_calls: int = 0
    notes: list[str] = field(default_factory=list)  # e.g. citations removed by the validator


CitationValidator = Callable[[InvestigationAnswer, set[str]], InvestigationAnswer]


def send_event(on_event: ProgressCallback | None, event: dict) -> None:
    """Report progress if someone is listening.

    Design decision: a failing on_event must NOT crash the agent. Progress is only a display; a broken display
    (e.g. a closed browser connection) should not throw away a correct answer that costs several LLM calls.
    So the error is logged and the investigation continues.
    """
    if on_event is None:
        return
    try:
        on_event(event)
    except Exception:
        logger.exception("on_event failed for a %r event; continuing without it", event.get("type"))


def describe_tool_result(tool_name: str, result: dict) -> dict:
    """A small, JSON-serializable summary of a tool result: which documents it found, or what went wrong."""
    titles = [str(item.get("title", "")) for item in result.get("results", [])]  # search_documents
    if "title" in result:  # read_document returns one document
        titles.append(str(result["title"]))
    error = result.get("error")
    return {"type": "tool_result", "tool": tool_name, "titles": titles, "error": str(error) if error else None}


def extract_json_object(text: str) -> dict:
    """Parse the model's final answer. Tolerates ```json fences or a sentence around the object."""
    start, end = text.find("{"), text.rfind("}")
    if start == -1 or end <= start:
        raise ValueError("no JSON object in the reply")
    parsed = json.loads(text[start:end + 1])
    if not isinstance(parsed, dict):
        raise ValueError("the reply is not a JSON object")
    return parsed


def parse_final_answer(question: str, text: str) -> InvestigationAnswer:
    parsed = extract_json_object(text)
    return InvestigationAnswer(
        question=question,
        answer=str(parsed.get("answer") or ""),
        claims=[Claim(str(item.get("text", "")), [str(chunk_id) for chunk_id in item.get("citations") or []])
                for item in parsed.get("claims") or [] if isinstance(item, dict)],
        conflicts=[Conflict(str(item.get("description", "")), [str(chunk_id) for chunk_id in item.get("citations") or []])
                   for item in parsed.get("conflicts") or [] if isinstance(item, dict)],
        should_abstain=bool(parsed.get("should_abstain", False)),
        abstain_reason=str(parsed.get("abstain_reason") or ""),
    )


class InvestigationAgent:
    def __init__(self, llm: LLMProvider, create_tool_executor: Callable[[], ToolExecutor],
                 validate_citations: CitationValidator | None = None, max_tool_steps: int = MAX_TOOL_STEPS):
        self.llm = llm
        self.create_tool_executor = create_tool_executor  # a fresh executor (and evidence log) per question
        self.validate_citations = validate_citations
        self.max_tool_steps = max_tool_steps
        self.system_prompt = build_system_prompt()

    def answer(self, question: str, on_event: ProgressCallback | None = None) -> InvestigationAnswer:
        """Raises LLMError if the LLM is unreachable even after retries (the API turns that into an error response).

        on_event, if given, is called with progress events: started, then tool_call / tool_result per tool use.
        """
        send_event(on_event, {"type": "started", "question": question})
        tool_executor = self.create_tool_executor()
        messages = [Message(role="user", text=question)]
        llm_calls = 0
        fallback_notes: list[str] = []  # filled when the backup model wrote a reply (rag/llm.py FallbackProvider)

        for _ in range(self.max_tool_steps):
            reply = self.generate_reply(messages, AGENT_TOOLS, fallback_notes)
            llm_calls += 1
            messages.append(Message.from_reply(reply))
            if not reply.tool_calls:
                return self.finish(question, messages, reply.text, tool_executor, llm_calls, fallback_notes)
            for tool_call in reply.tool_calls:
                send_event(on_event, {"type": "tool_call", "tool": tool_call.name,
                                      "arguments": dict(tool_call.arguments)})
                result = tool_executor.execute(tool_call)
                send_event(on_event, describe_tool_result(tool_call.name, result))
                messages.append(Message(role="tool", tool_name=tool_call.name, tool_result=result))

        # Step limit reached: ask for the final answer with no tools available.
        messages.append(Message(role="user", text=FINAL_ANSWER_REMINDER))
        reply = self.generate_reply(messages, [], fallback_notes)
        llm_calls += 1
        messages.append(Message.from_reply(reply))
        return self.finish(question, messages, reply.text, tool_executor, llm_calls, fallback_notes)

    def generate_reply(self, messages: list[Message], tools: list[ToolSpec], fallback_notes: list[str]) -> LLMReply:
        """One LLM call; if the backup model answered it, remember why (once per reason) for the answer's notes."""
        reply = self.llm.generate(self.system_prompt, messages, tools)
        if reply.fallback_reason and reply.fallback_reason not in fallback_notes:
            fallback_notes.append(reply.fallback_reason)
        return reply

    def finish(self, question: str, messages: list[Message], final_text: str, tool_executor: ToolExecutor,
               llm_calls: int, fallback_notes: list[str]) -> InvestigationAnswer:
        try:
            answer = parse_final_answer(question, final_text)
        except ValueError:
            # One more try before giving up: the evaluation saw an empty final reply turn a question into an
            # abstention. Empty assistant turns are left out, because the API can reject a message with no content.
            repair_messages = [message for message in messages
                               if message.role != "assistant" or message.text or message.tool_calls]
            repair_messages.append(Message(role="user", text=FORMAT_REPAIR_REMINDER))
            repair_reply = self.generate_reply(repair_messages, [], fallback_notes)
            llm_calls += 1
            try:
                answer = parse_final_answer(question, repair_reply.text)
                answer.notes.append("final reply was invalid on the first attempt and repaired by one retry")
            except ValueError:
                answer = InvestigationAnswer(
                    question=question, should_abstain=True, abstain_reason=INVALID_FORMAT_REASON,
                    notes=[f"unparseable final reply: {final_text[:200]!r}; after one retry: {repair_reply.text[:200]!r}"])
        answer.search_queries = list(tool_executor.search_queries)
        answer.retrieved_chunk_ids = list(tool_executor.retrieved_chunks)
        answer.source_titles = {chunk_id: chunk.title for chunk_id, chunk in tool_executor.retrieved_chunks.items()}
        answer.llm_calls = llm_calls
        answer.notes = fallback_notes + answer.notes

        validate_citations = self.validate_citations
        if validate_citations is None:
            from casefile.rag.citations import validate_citations  # written as task U2
        return validate_citations(answer, set(tool_executor.retrieved_chunks))
