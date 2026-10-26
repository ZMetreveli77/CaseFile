import json

import pytest

from casefile.evaluation.answer_eval import answer_with_single_search, judge_answer, score_answer, summarize_answers
from casefile.ingestion.pipeline import IngestionPipeline
from casefile.rag.agent import Claim, InvestigationAnswer
from casefile.rag.citations import validate_citations
from casefile.rag.llm import LLMReply
from casefile.retrieval.search import HybridSearcher
from tests.fakes import FakeLLM

HOTEL_TEXT = "The Lighthouse Hotel in Port Ellis was built in 1902 by Margaret Hale."
ANSWERABLE = {"id": "q1", "category": "simple", "answer": "Margaret Hale", "supporting_titles": ["hotel.txt"]}


def make_answer(answer="Margaret Hale", should_abstain=False, cited=("c1",), titles=None):
    return InvestigationAnswer(question="q", answer=answer, should_abstain=should_abstain,
                               claims=[Claim("fact", list(cited))] if cited else [],
                               source_titles=titles or {"c1": "hotel.txt", "c2": "other.txt"}, llm_calls=2,
                               search_queries=["a", "b"])


def test_correct_cited_answer_scores_well():
    scores = score_answer(ANSWERABLE, make_answer(), {"correct": True, "reason": ""})
    assert scores["exact_match"] and scores["f1"] == 1.0 and scores["correct"]
    assert scores["evidence_retrieved"] and scores["citation_precision"] == 1.0 and scores["citation_recall"] == 1.0


def test_wrong_citation_lowers_citation_precision():
    scores = score_answer(ANSWERABLE, make_answer(cited=("c1", "c2")), {"correct": True, "reason": ""})
    assert scores["citation_precision"] == 0.5 and scores["citation_recall"] == 1.0


def test_abstaining_on_an_answerable_question_is_wrong_and_has_no_citation_scores():
    scores = score_answer(ANSWERABLE, make_answer(answer="", should_abstain=True, cited=()), None)
    assert scores["abstained"] and not scores["correct"]
    assert scores["citation_precision"] is None and scores["citation_recall"] is None


def test_unanswerable_question_is_correct_only_when_abstaining():
    unanswerable = {"id": "u1", "category": "unanswerable", "answer": None, "supporting_titles": []}
    assert score_answer(unanswerable, make_answer(answer="", should_abstain=True, cited=()), None)["correct"]
    assert not score_answer(unanswerable, make_answer(), None)["correct"]


def test_summary_computes_abstention_precision_and_recall():
    results = [
        {"category": "unanswerable", "scores": {"abstained": True, "correct": True, "llm_calls": 1, "searches": 1}},
        {"category": "unanswerable", "scores": {"abstained": False, "correct": False, "llm_calls": 1, "searches": 1}},
        {"category": "simple", "scores": {"abstained": True, "correct": False, "llm_calls": 1, "searches": 1}},
    ]
    summary = summarize_answers(results)
    assert summary["abstention_recall"] == 0.5  # 1 of 2 unanswerable questions refused
    assert summary["abstention_precision"] == 0.5  # 1 of 2 refusals was justified
    assert summary["false_abstention_rate"] == 1.0  # the one answerable question was refused


def test_judge_parses_its_verdict_and_handles_garbage():
    assert judge_answer(FakeLLM([LLMReply(text='{"correct": true, "reason": "same"}')]), "q", "a", "a")["correct"] is True
    assert judge_answer(FakeLLM([LLMReply(text="I think so")]), "q", "a", "a")["correct"] is None
    assert judge_answer(FakeLLM([]), "q", "a", "  ")["correct"] is False  # empty answer: no LLM call needed


def test_single_search_baseline_answers_from_one_search_with_valid_citations(qdrant_store, embedder):
    IngestionPipeline(qdrant_store).ingest_file("hotel.txt", HOTEL_TEXT.encode())
    searcher = HybridSearcher(qdrant_store, embedder)
    [result] = searcher.search("Lighthouse Hotel", top_k=1)
    final = {"answer": "Margaret Hale", "claims": [{"text": "Built by Margaret Hale.",
                                                    "citations": [result.chunk.chunk_id, "invented-id"]}]}
    llm = FakeLLM([LLMReply(text=json.dumps(final))])
    answer = answer_with_single_search(llm, searcher, "Who built the Lighthouse Hotel?", validate_citations)
    assert answer.answer == "Margaret Hale" and answer.llm_calls == 1
    assert answer.claims[0].citations == [result.chunk.chunk_id]  # the invented id was removed by the validator
    assert llm.requests[0][1] == []  # no tools offered: one search only
    assert answer.search_queries == ["Who built the Lighthouse Hotel?"]


@pytest.mark.parametrize("category", ["bridge", "comparison", "simple"])
def test_every_answerable_category_gets_answer_scores(category):
    scores = score_answer({**ANSWERABLE, "category": category}, make_answer(), {"correct": True, "reason": ""})
    assert "f1" in scores and "citation_precision" in scores
