"""Retrieval metrics: did the search put the paragraphs that prove the answer near the top?

`ranked_ids` is what the system returned, best first (e.g. the titles of the retrieved chunks).
`relevant_ids` is what it should have found (e.g. a HotpotQA question's supporting_titles).
"""
import re
import string
from collections import Counter

PUNCTUATION_TABLE = str.maketrans("", "", string.punctuation)  # deletes every ASCII punctuation character
ARTICLE_PATTERN = re.compile(r"\b(a|an|the)\b")  # \b = word boundary: only whole words, "theater" survives
YES_NO_ANSWERS = frozenset({"yes", "no"})  # comparison questions: a different yes/no is simply wrong, no partial credit
from collections.abc import Iterable


def check_metric_inputs(relevant_ids: Iterable[str], k: int | None = None) -> set[str]:
    """Shared rules for every metric: relevant_ids must not be empty, and k must be at least 1."""
    relevant_set = set(relevant_ids)
    if not relevant_set:
        raise ValueError("relevant_ids is empty: retrieval metrics are undefined for a question with no evidence "
                         "(score unanswerable questions by abstention instead)")
    if k is not None and k < 1:
        raise ValueError(f"k must be at least 1, got {k}")
    return relevant_set


def recall_at_k(ranked_ids: list[str], relevant_ids: Iterable[str], k: int) -> float:
    """Fraction of the relevant ids that appear in the first k positions of ranked_ids.

    Decisions:
    - Empty relevant_ids raises ValueError. With nothing to find, recall is undefined; returning 1.0 or 0.0 would
      silently push the average up or down. Unanswerable questions are measured by abstention, not by recall.
    - k bigger than the list: the whole list is used (Python slicing), no error. A system that returned fewer
      results than k simply had fewer chances.
    - Duplicates count once: the result is a SET intersection, so a title retrieved via three chunks is one hit, and
      recall can never exceed 1.0. k counts positions in ranked_ids as returned, so duplicates still use up slots.
    """
    relevant_set = check_metric_inputs(relevant_ids, k)
    found = relevant_set & set(ranked_ids[:k])
    return len(found) / len(relevant_set)


def all_found_at_k(ranked_ids: list[str], relevant_ids: Iterable[str], k: int) -> bool:
    """True only if EVERY relevant id is in the first k positions.

    The strict version of recall for multi-hop questions: with only one of two supporting paragraphs, the answer
    cannot be proven. Same decisions as recall_at_k (empty relevant_ids raises, big k is fine, duplicates once).
    """
    return recall_at_k(ranked_ids, relevant_ids, k) == 1.0


def reciprocal_rank(ranked_ids: list[str], relevant_ids: Iterable[str]) -> float:
    """1 / position of the FIRST relevant id (rank 1 -> 1.0, rank 2 -> 0.5, ...); 0.0 if none is found.

    Decisions: empty relevant_ids raises ValueError (as above). There is no k: the whole list is searched.
    Duplicates don't matter, because only the first hit counts. Averaged over questions, this is MRR.
    """
    relevant_set = check_metric_inputs(relevant_ids)
    for rank, ranked_id in enumerate(ranked_ids, start=1):
        if ranked_id in relevant_set:
            return 1.0 / rank
    return 0.0


def mean(values: Iterable[float]) -> float:
    """Average of the values; 0.0 for an empty list (e.g. a category with no questions in this split).

    Unlike statistics.mean, this does not raise on an empty input, so a report with an empty category still prints.
    """
    values = list(values)
    return sum(values) / len(values) if values else 0.0


def normalize_answer(text: str) -> str:
    """HotpotQA's answer normalization, so "The U.S. Chief of Protocol." and "us chief of protocol" compare equal.

    Order matters: lowercase -> remove punctuation -> remove the articles a/an/the -> collapse whitespace.
    Punctuation is deleted, not replaced by a space, so "U.S." becomes "us" (as in the official script).
    """
    text = text.lower()
    text = text.translate(PUNCTUATION_TABLE)
    text = ARTICLE_PATTERN.sub(" ", text)
    return " ".join(text.split())  # split() with no argument splits on any run of spaces, tabs and newlines


def exact_match(predicted: str, gold: str) -> bool:
    """True if the two answers are identical after normalize_answer."""
    return normalize_answer(predicted) == normalize_answer(gold)


def token_f1(predicted: str, gold: str) -> float:
    """Word-overlap F1 between two answers (HotpotQA's official answer F1), from 0.0 to 1.0.

    precision = shared words / words in the prediction, recall = shared words / words in the gold answer,
    F1 = their harmonic mean. Gives partial credit: "Greenwich Village, New York City" vs "Greenwich Village" -> 0.571.
    - Yes/no rule: if either answer is "yes" or "no" and they differ, F1 is 0.0. Otherwise "no" vs "no it is not"
      would earn partial credit for the opposite answer.
    - Repeated words: Counter & Counter keeps the MINIMUM count of each word, so a word only counts as shared as often
      as it appears in BOTH answers ("new york new york" vs "new york" shares 2 words, not 4).
    - Nothing shared (including an empty answer) -> 0.0, as in the official script.
    """
    predicted_normalized, gold_normalized = normalize_answer(predicted), normalize_answer(gold)
    is_yes_no_question = predicted_normalized in YES_NO_ANSWERS or gold_normalized in YES_NO_ANSWERS
    if is_yes_no_question and predicted_normalized != gold_normalized:
        return 0.0
    predicted_words, gold_words = predicted_normalized.split(), gold_normalized.split()
    shared_count = sum((Counter(predicted_words) & Counter(gold_words)).values())
    if shared_count == 0:
        return 0.0
    precision = shared_count / len(predicted_words)
    recall = shared_count / len(gold_words)
    return 2 * precision * recall / (precision + recall)


def citation_precision(cited_titles: list[str], supporting_titles: set[str]) -> float:
    """Of the distinct documents the answer cites, the fraction that really support it (0.0 to 1.0).

    Decisions:
    - The same document cited twice counts once (distinct titles), so repeating a good citation can't raise the score.
    - Nothing cited -> 0.0. An answer without evidence is unsupported, which is the worst case, not a perfect one;
      returning 1.0 would reward citing nothing. (An abstention cites nothing too: score abstentions separately and
      leave them out of this average, like unanswerable questions are left out of recall.)
    """
    distinct_cited = set(cited_titles)
    if not distinct_cited:
        return 0.0
    return len(distinct_cited & supporting_titles) / len(distinct_cited)


def citation_recall(cited_titles: list[str], supporting_titles: set[str]) -> float:
    """Of the documents that support the answer, the fraction the answer cites (0.0 to 1.0).

    Decisions:
    - The same document cited twice counts once (distinct titles).
    - No supporting titles (e.g. unanswerable questions) raises ValueError: with nothing to cite, recall is undefined,
      and 0.0 or 1.0 would silently bias the average. Same rule as recall_at_k.
    """
    supporting_set = check_metric_inputs(supporting_titles)
    return len(set(cited_titles) & supporting_set) / len(supporting_set)