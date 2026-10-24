"""Own Reciprocal Rank Fusion (RRF): merge ranked lists using ranks only, so different score scales don't matter.

RRF(item) = sum over lists of  weight / (RRF_RANK_CONSTANT + rank)     (rank starts at 1)
"""
from collections import defaultdict

RRF_RANK_CONSTANT = 60  # from the original RRF paper (Cormack et al., 2009); damps the top ranks


def combine_search_results(ranked_lists: list[list[str]], weights: list[float] | None = None,
                           rank_constant: int = RRF_RANK_CONSTANT) -> list[tuple[str, float]]:
    """Return (item_id, fused_score) sorted best first. Ties keep first-seen order (stable)."""
    weights = weights or [1.0] * len(ranked_lists)
    if len(weights) != len(ranked_lists):
        raise ValueError("need one weight per ranked list")
    fused_scores: dict[str, float] = defaultdict(float)
    for ranked_ids, weight in zip(ranked_lists, weights):
        for rank, item_id in enumerate(ranked_ids, start=1):
            fused_scores[item_id] += weight / (rank_constant + rank)
    return sorted(fused_scores.items(), key=lambda item: item[1], reverse=True)
