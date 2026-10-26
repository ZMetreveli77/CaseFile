import pytest

from casefile.evaluation.metrics import (all_found_at_k, citation_precision, citation_recall, exact_match, mean,
                                         normalize_answer, recall_at_k, reciprocal_rank, token_f1)

RANKED_TITLES = ["Kiss and Tell (1945 film)", "Paris", "Berlin", "Shirley Temple", "Rome"]
SUPPORTING_TITLES = ["Kiss and Tell (1945 film)", "Shirley Temple"]


def test_recall_is_the_fraction_of_relevant_ids_in_the_top_k():
    assert recall_at_k(RANKED_TITLES, SUPPORTING_TITLES, k=3) == 0.5  # 2 relevant, 1 in the top 3
    assert recall_at_k(RANKED_TITLES, SUPPORTING_TITLES, k=4) == 1.0
    assert recall_at_k(RANKED_TITLES, ["Tokyo"], k=5) == 0.0


def test_all_found_at_k_needs_every_relevant_id():
    assert all_found_at_k(RANKED_TITLES, SUPPORTING_TITLES, k=3) is False  # only one of the two
    assert all_found_at_k(RANKED_TITLES, SUPPORTING_TITLES, k=4) is True


def test_reciprocal_rank_uses_the_first_hit():
    assert reciprocal_rank(["Paris", "Shirley Temple", "Kiss and Tell (1945 film)"], SUPPORTING_TITLES) == 0.5
    assert reciprocal_rank(RANKED_TITLES, SUPPORTING_TITLES) == 1.0
    assert reciprocal_rank(["Paris", "Rome"], SUPPORTING_TITLES) == 0.0


def test_mean_of_nothing_is_zero():
    assert mean([]) == 0.0
    assert mean([1.0, 0.5, 0.0]) == 0.5


def test_k_bigger_than_the_list_uses_the_whole_list():
    assert recall_at_k(["Shirley Temple"], SUPPORTING_TITLES, k=100) == 0.5


def test_duplicate_ids_count_once():
    # One paragraph retrieved through two of its chunks is still one hit, so recall can never exceed 1.0.
    assert recall_at_k(["Shirley Temple", "Shirley Temple"], SUPPORTING_TITLES, k=2) == 0.5
    assert recall_at_k(["Shirley Temple", "Shirley Temple", "Kiss and Tell (1945 film)"], SUPPORTING_TITLES, k=2) == 0.5


def test_empty_relevant_ids_and_bad_k_are_rejected():
    with pytest.raises(ValueError):
        recall_at_k(RANKED_TITLES, [], k=5)
    with pytest.raises(ValueError):
        reciprocal_rank(RANKED_TITLES, [])
    with pytest.raises(ValueError):
        recall_at_k(RANKED_TITLES, SUPPORTING_TITLES, k=0)


def test_normalize_answer_follows_the_hotpotqa_recipe():
    assert normalize_answer("The U.S. Chief of Protocol.") == "us chief of protocol"


def test_normalize_answer_collapses_spaces_and_tabs():
    assert normalize_answer("  Chief \t of\t\tProtocol \n") == "chief of protocol"


def test_normalize_answer_removes_articles_only_as_whole_words():
    assert normalize_answer("The theater") == "theater"  # "the" inside "theater" survives
    assert normalize_answer("An answer, a banana and another") == "answer banana and another"


def test_identical_answers_after_normalization_match_exactly():
    assert exact_match("The U.S. Chief of Protocol.", "us chief of protocol") is True
    assert token_f1("The U.S. Chief of Protocol.", "us chief of protocol") == 1.0


def test_partial_answer_gets_partial_f1_but_no_exact_match():
    assert exact_match("Greenwich Village, New York City", "Greenwich Village") is False
    # 2 shared words; precision 2/5, recall 2/2 -> F1 = 2 * 0.4 * 1.0 / 1.4
    assert token_f1("Greenwich Village, New York City", "Greenwich Village") == pytest.approx(0.571, abs=0.001)


def test_nothing_in_common_gives_zero_f1():
    assert token_f1("Chief of Protocol", "Greenwich Village") == 0.0


def test_different_yes_no_answers_get_zero_f1():
    assert token_f1("yes", "no") == 0.0
    assert token_f1("no it is not", "no") == 0.0  # would share "no" without the yes/no rule
    assert token_f1("Yes.", "yes") == 1.0


def test_repeated_words_are_counted_as_often_as_they_appear_in_both():
    # Shared: "new" once and "york" once (the minimum counts), so precision 2/4, recall 2/2 -> F1 2/3.
    assert token_f1("New York New York", "New York") == pytest.approx(2 / 3)


def test_citation_precision_is_the_share_of_cited_documents_that_support():
    assert citation_precision(["Shirley Temple", "Paris"], set(SUPPORTING_TITLES)) == 0.5


def test_citation_recall_is_the_share_of_supporting_documents_cited():
    assert citation_recall(["Kiss and Tell (1945 film)", "Shirley Temple"], set(SUPPORTING_TITLES)) == 1.0
    assert citation_recall(["Shirley Temple"], set(SUPPORTING_TITLES)) == 0.5


def test_nothing_cited_gives_zero_precision_and_recall():
    assert citation_precision([], set(SUPPORTING_TITLES)) == 0.0
    assert citation_recall([], set(SUPPORTING_TITLES)) == 0.0


def test_no_supporting_titles_makes_citation_recall_undefined():
    with pytest.raises(ValueError):
        citation_recall(["Paris"], set())


def test_the_same_document_cited_twice_counts_once():
    assert citation_precision(["Shirley Temple", "Shirley Temple", "Paris"], set(SUPPORTING_TITLES)) == 0.5
    assert citation_recall(["Shirley Temple", "Shirley Temple"], set(SUPPORTING_TITLES)) == 0.5