from casefile.models import Chunk, SearchResult
from casefile.retrieval.rerank import measure_overlap, measure_query_coverage, rerank_results


def make_result(chunk_id, doc_id, text, score):
    return SearchResult(Chunk(chunk_id=chunk_id, doc_id=doc_id, index=0, text=text), score)


def test_coverage_and_overlap():
    assert measure_query_coverage({"payment", "march"}, {"payment", "failed"}) == 0.5
    assert measure_query_coverage(set(), {"payment"}) == 0.0
    assert measure_overlap({"a", "b"}, {"b", "c"}) == 1 / 3


def weak_tail(count=3):
    """Low-ranked unrelated candidates, as in a real pool of top_k * 4 RRF results."""
    return [make_result(f"tail{number}", f"tail{number}", f"unrelated filler note {number}", 1 / (75 + number))
            for number in range(count)]


def test_chunk_covering_more_query_terms_moves_up():
    # Realistic RRF scores: two close top candidates plus a weak tail.
    candidates = [
        make_result("1", "doc1", "the payment service was slow", 1 / 61),
        make_result("2", "doc2", "payment outage in march caused by chg-42", 1 / 62),
        *weak_tail(),
    ]
    reranked = rerank_results("payment outage march chg-42", candidates, top_k=2)
    assert reranked[0].chunk.chunk_id == "2"
    assert reranked[0].details["coverage"] == 1.0


def test_mmr_prefers_a_second_document_over_a_near_copy():
    candidates = [
        make_result("1", "doc1", "checkout api outage march payments", 1 / 61),
        make_result("2", "doc1", "checkout api outage march payments again", 1 / 62),
        make_result("3", "doc2", "invoicing service affected by outage", 1 / 64),
        *weak_tail(),
    ]
    reranked = rerank_results("checkout outage", candidates, top_k=2)
    assert [result.chunk.doc_id for result in reranked] == ["doc1", "doc2"]


def test_close_rrf_scores_do_not_let_diversity_pick_an_unrelated_chunk():
    # Regression: with scores 1/61, 1/62, 1/63 and divide-by-max normalisation, the unrelated
    # offsite note (zero overlap with the top result) beat the relevant change log.
    candidates = [
        make_result("1", "incident", "checkout api went down march root cause change chg-42 load balancer", 1 / 61),
        make_result("2", "changes", "change log chg-42 raised load balancer timeout chg-43 invoice template", 1 / 62),
        make_result("3", "offsite", "team offsite notes hiring plans office move may", 1 / 63),
    ]
    reranked = rerank_results("why did payments stop working", candidates, top_k=2)
    assert [result.chunk.doc_id for result in reranked] == ["incident", "changes"]


def test_top_k_and_empty():
    candidates = [make_result(str(number), f"d{number}", f"text {number}", 1.0) for number in range(5)]
    assert len(rerank_results("text", candidates, top_k=3)) == 3
    assert rerank_results("anything", [], top_k=3) == []
