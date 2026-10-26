import random

from casefile.evaluation.eval_set import (BRIDGE_COUNT, COMPARISON_COUNT, UNANSWERABLE_QUESTIONS, assign_splits,
                                          build_unanswerable_items, find_spot_check_ids, pick_simple_paragraphs,
                                          sample_hotpot_questions)


def make_questions(count_per_type=40):
    return [{"id": f"{question_type}-{number}", "type": question_type, "question": f"q {number}?", "answer": "a",
             "supporting_titles": [f"{question_type} title {number}"]}
            for question_type in ("bridge", "comparison") for number in range(count_per_type)]


def test_spot_check_questions_are_the_first_per_type():
    assert find_spot_check_ids(make_questions()) == {"bridge-0", "bridge-1", "bridge-2", "comparison-0", "comparison-1"}


def test_sample_has_the_right_counts_excludes_spot_check_and_is_reproducible():
    questions = make_questions()
    first = sample_hotpot_questions(questions, random.Random(1))
    assert sum(item["category"] == "bridge" for item in first) == BRIDGE_COUNT
    assert sum(item["category"] == "comparison" for item in first) == COMPARISON_COUNT
    assert not {item["id"] for item in first} & find_spot_check_ids(questions)
    assert sample_hotpot_questions(questions, random.Random(1)) == first  # same seed -> same set


def test_simple_paragraphs_respect_length_and_exclusions():
    corpus = [{"title": f"t{number}", "text": "x" * length} for number, length in enumerate([100, 400, 500, 900, 600])]
    picked = pick_simple_paragraphs(corpus, 2, random.Random(1), excluded_titles={"t2"})
    assert {paragraph["title"] for paragraph in picked} <= {"t1", "t4"}


def test_unanswerable_items_have_no_answer_and_no_supporting_titles():
    items = build_unanswerable_items()
    assert len(items) == len(UNANSWERABLE_QUESTIONS)
    assert all(item["answer"] is None and item["supporting_titles"] == [] for item in items)
    assert len({item["id"] for item in items}) == len(items)


def test_every_category_is_split_in_half():
    items = [{"category": category, "id": f"{category}-{number}"} for category in ("a", "b") for number in range(10)]
    assign_splits(items, random.Random(1))
    for category in ("a", "b"):
        splits = [item["split"] for item in items if item["category"] == category]
        assert splits.count("dev") == 5 and splits.count("test") == 5
