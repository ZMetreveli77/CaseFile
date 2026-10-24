import pytest

from casefile.retrieval.fusion import combine_search_results


def test_item_found_by_both_lists_wins():
    dense_ranking = ["a", "b", "c"]
    sparse_ranking = ["d", "b", "e"]
    fused_ids = [item_id for item_id, _ in combine_search_results([dense_ranking, sparse_ranking])]
    assert fused_ids[0] == "b"
    assert set(fused_ids) == {"a", "b", "c", "d", "e"}


def test_scores_follow_formula():
    [(item_id, score)] = combine_search_results([["x"]], rank_constant=60)
    assert item_id == "x" and score == pytest.approx(1 / 61)


def test_weights_shift_the_ranking():
    dense_ranking, sparse_ranking = ["a"], ["b"]
    favour_sparse = combine_search_results([dense_ranking, sparse_ranking], weights=[0.5, 1.0])
    assert favour_sparse[0][0] == "b"


def test_weight_count_must_match():
    with pytest.raises(ValueError):
        combine_search_results([["a"], ["b"]], weights=[1.0])
