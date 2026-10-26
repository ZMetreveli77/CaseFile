"""Answer-level evaluation: a one-search baseline, an LLM judge, and per-question scores using metrics.py.

Categories are scored differently:
- bridge / comparison / simple: correctness (exact match, token F1, LLM judge), whether the evidence was retrieved,
  and citation precision/recall (only for answers that didn't abstain);
- unanswerable: a correct abstention is the right answer;
- contradictory (task H2): whether the conflict was reported.
"""
import json

from casefile.evaluation.metrics import citation_precision, citation_recall, exact_match, mean, token_f1
from casefile.rag.agent import INVALID_FORMAT_REASON, CitationValidator, InvestigationAnswer, parse_final_answer
from casefile.rag.llm import LLMProvider, Message
from casefile.rag.prompts import build_system_prompt
from casefile.retrieval.search import HybridSearcher

ANSWERABLE_CATEGORIES = ("bridge", "comparison", "simple")
BASELINE_RESULTS = 6  # same number of passages the agent's search tool returns per call

JUDGE_PROMPT = """You grade a question-answering system. Decide whether the PREDICTED answer means the same as the
GOLD answer for this question. Different wording, abbreviations, or extra correct detail are fine. A missing or wrong
key fact, or a different yes/no, is incorrect. Reply with ONLY this JSON: {"correct": true or false, "reason": "..."}"""


def answer_with_single_search(llm: LLMProvider, searcher: HybridSearcher, question: str,
                              validate_citations: CitationValidator) -> InvestigationAnswer:
    """Baseline: ONE search with the question itself, then one LLM call with the passages; no tools, no second search.
    Same system prompt, rules and answer format as the agent, so the only difference is the multi-step search."""
    results = searcher.search(question, top_k=BASELINE_RESULTS)
    passages = [{"chunk_id": result.chunk.chunk_id, "title": result.chunk.title, "text": result.chunk.text}
                for result in results]
    user_text = (f"Question: {question}\n\nYou cannot search. These passages are all the evidence you have:\n"
                 f"{json.dumps(passages, ensure_ascii=False)}")
    reply = llm.generate(build_system_prompt(), [Message(role="user", text=user_text)], tools=[])
    try:
        answer = parse_final_answer(question, reply.text)
    except ValueError:
        answer = InvestigationAnswer(question=question, should_abstain=True, abstain_reason=INVALID_FORMAT_REASON)
    answer.search_queries = [question]
    answer.retrieved_chunk_ids = [passage["chunk_id"] for passage in passages]
    answer.source_titles = {passage["chunk_id"]: passage["title"] for passage in passages}
    answer.llm_calls = 1
    return validate_citations(answer, set(answer.retrieved_chunk_ids))


def judge_answer(llm: LLMProvider, question: str, gold: str, predicted: str) -> dict:
    """LLM-as-judge for meaning-level correctness. Returns {"correct": bool | None, "reason": str}."""
    if not predicted.strip():
        return {"correct": False, "reason": "empty answer"}
    reply = llm.generate(JUDGE_PROMPT, [Message(role="user", text=f"QUESTION: {question}\nGOLD: {gold}\n"
                                                                  f"PREDICTED: {predicted}")], tools=[])
    try:
        verdict = json.loads(reply.text[reply.text.find("{"):reply.text.rfind("}") + 1])
        return {"correct": bool(verdict["correct"]), "reason": str(verdict.get("reason", ""))}
    except (ValueError, KeyError):
        return {"correct": None, "reason": f"unparseable judge reply: {reply.text[:120]!r}"}


def score_answer(item: dict, answer: InvestigationAnswer, judge_verdict: dict | None) -> dict:
    """Scores for one question. Values are None when a metric doesn't apply (so averages skip them)."""
    category = item["category"]
    cited_titles = [answer.source_titles.get(chunk_id, chunk_id) for claim in answer.claims for chunk_id in claim.citations]
    retrieved_titles = set(answer.source_titles.values())
    scores = {"abstained": answer.should_abstain, "llm_calls": answer.llm_calls, "searches": len(answer.search_queries)}
    if category == "unanswerable":
        scores["correct"] = answer.should_abstain
        return scores
    if category == "contradictory":
        scores["conflict_reported"] = bool(answer.conflicts)
        return scores
    supporting_titles = set(item["supporting_titles"])
    scores["evidence_retrieved"] = supporting_titles <= retrieved_titles  # every supporting paragraph was seen
    scores["exact_match"] = exact_match(answer.answer, item["answer"])
    scores["f1"] = token_f1(answer.answer, item["answer"])
    scores["judge_correct"] = judge_verdict["correct"] if judge_verdict else None
    scores["correct"] = bool(scores["judge_correct"]) and not answer.should_abstain
    scores["citation_precision"] = None if answer.should_abstain else citation_precision(cited_titles, supporting_titles)
    scores["citation_recall"] = None if answer.should_abstain else citation_recall(cited_titles, supporting_titles)
    return scores


def average(results: list[dict], metric: str) -> float | None:
    values = [float(result["scores"][metric]) for result in results if result["scores"].get(metric) is not None]
    return round(mean(values), 3) if values else None


def summarize_answers(results: list[dict]) -> dict:
    answerable = [result for result in results if result["category"] in ANSWERABLE_CATEGORIES]
    unanswerable = [result for result in results if result["category"] == "unanswerable"]
    abstained = [result for result in results if result["scores"]["abstained"]]
    correct_abstentions = [result for result in unanswerable if result["scores"]["abstained"]]
    return {
        "questions": len(results),
        "answer_accuracy_judge": average(answerable, "correct"),
        "exact_match": average(answerable, "exact_match"),
        "f1": average(answerable, "f1"),
        "evidence_retrieved": average(answerable, "evidence_retrieved"),
        "citation_precision": average(answerable, "citation_precision"),
        "citation_recall": average(answerable, "citation_recall"),
        "false_abstention_rate": average(answerable, "abstained"),
        # Abstention precision: of all abstentions, how many were on unanswerable questions (no needless refusals).
        "abstention_precision": round(len(correct_abstentions) / len(abstained), 3) if abstained else None,
        # Abstention recall: of the unanswerable questions, how many were refused (no invented answers).
        "abstention_recall": round(len(correct_abstentions) / len(unanswerable), 3) if unanswerable else None,
        "conflict_detection": average([result for result in results if result["category"] == "contradictory"],
                                      "conflict_reported"),
        "llm_calls_per_question": average(results, "llm_calls"),
        "searches_per_question": average(results, "searches"),
    }
