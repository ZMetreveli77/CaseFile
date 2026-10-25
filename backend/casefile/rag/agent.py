"""Multi-step investigation agent: the LLM searches, reads, searches again, then answers with citations.

Loop: LLM reply -> if it asks for tools, run them and send the results back -> repeat, at most MAX_TOOL_STEPS times
-> parse the final JSON answer -> keep only citations that point at chunks the agent actually retrieved.
"""
import json
from dataclasses import dataclass, field
from typing import Callable

from casefile.rag.llm import LLMProvider, Message
from casefile.rag.prompts import FINAL_ANSWER_REMINDER, build_system_prompt
from casefile.rag.tools import AGENT_TOOLS, ToolExecutor

MAX_TOOL_STEPS = 5  # rounds of tool use per question: enough for 2-hop questions, bounded cost on the free tier
INVALID_FORMAT_REASON = "The model did not return a valid answer, so no answer is given."


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

    def answer(self, question: str) -> InvestigationAnswer:
        """Raises LLMError if the LLM is unreachable even after retries (the API turns that into an error response)."""
        tool_executor = self.create_tool_executor()
        messages = [Message(role="user", text=question)]
        llm_calls = 0

        for _ in range(self.max_tool_steps):
            reply = self.llm.generate(self.system_prompt, messages, AGENT_TOOLS)
            llm_calls += 1
            messages.append(Message.from_reply(reply))
            if not reply.tool_calls:
                return self.finish(question, reply.text, tool_executor, llm_calls)
            for tool_call in reply.tool_calls:
                result = tool_executor.execute(tool_call)
                messages.append(Message(role="tool", tool_name=tool_call.name, tool_result=result))

        # Step limit reached: ask for the final answer with no tools available.
        messages.append(Message(role="user", text=FINAL_ANSWER_REMINDER))
        reply = self.llm.generate(self.system_prompt, messages, tools=[])
        llm_calls += 1
        return self.finish(question, reply.text, tool_executor, llm_calls)

    def finish(self, question: str, final_text: str, tool_executor: ToolExecutor, llm_calls: int) -> InvestigationAnswer:
        try:
            answer = parse_final_answer(question, final_text)
        except ValueError:
            answer = InvestigationAnswer(question=question, should_abstain=True, abstain_reason=INVALID_FORMAT_REASON,
                                         notes=[f"unparseable final reply: {final_text[:200]!r}"])
        answer.search_queries = list(tool_executor.search_queries)
        answer.retrieved_chunk_ids = list(tool_executor.retrieved_chunks)
        answer.source_titles = {chunk_id: chunk.title for chunk_id, chunk in tool_executor.retrieved_chunks.items()}
        answer.llm_calls = llm_calls

        validate_citations = self.validate_citations
        if validate_citations is None:
            from casefile.rag.citations import validate_citations  # written as task U2
        return validate_citations(answer, set(tool_executor.retrieved_chunks))
