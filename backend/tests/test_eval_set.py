import random

from casefile.evaluation.eval_set import (BRIDGE_COUNT, COMPARISON_COUNT, FALSE_PREMISE_TITLES, UNANSWERABLE_QUESTIONS,
                                          assign_splits, build_contradictory_items, build_unanswerable_items,
                                          find_contradiction_problems, find_single_year_fact, find_spot_check_ids,
                                          find_used_titles, pick_contradiction_paragraphs, pick_simple_paragraphs,
                                          sample_hotpot_questions)

PADDING = " It is known for many other things that have nothing to do with dates." * 6  # reach the minimum length


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


def make_paragraph(title, text):
    return {"id": title, "title": title, "text": text + PADDING}


def test_used_titles_include_supporting_titles_and_false_premise_paragraphs():
    eval_items = [{"supporting_titles": ["Roy Clark", "Jim Halsey"]}, {"supporting_titles": []}]
    used_titles = find_used_titles(eval_items)
    assert {"Roy Clark", "Jim Halsey"} <= used_titles
    assert FALSE_PREMISE_TITLES <= used_titles


def test_a_year_fact_needs_exactly_one_year_in_the_first_sentence():
    assert find_single_year_fact("GrocerKey was founded in 2015. It sells software.") == (
        "2015", "GrocerKey was founded in 2015.")
    assert find_single_year_fact("Born in 1950, she retired in 1999.") is None  # two different years
    assert find_single_year_fact("A band from Ohio. It formed in 1990.") is None  # year not in the first sentence
    assert find_single_year_fact("Population 19021 people.") is None  # not a year: no word boundary
    assert find_single_year_fact("Nevil Shute (17 January 189912 January 1960) was a novelist.") is None  # glued dates


def test_used_lists_and_year_titles_are_never_picked():
    corpus = [make_paragraph("Used Paragraph", "Used Paragraph opened in 1990."),
              make_paragraph("List of Things", "List of Things was made in 1991."),
              make_paragraph("Kaadu (1952 film)", "Kaadu is a 1952 film."),
              make_paragraph("Good Paragraph", "Good Paragraph was founded in 1993.")]
    picked = pick_contradiction_paragraphs(corpus, 1, random.Random(0), excluded_titles={"Used Paragraph"})
    assert [paragraph["title"] for paragraph in picked] == ["Good Paragraph"]
    assert picked[0]["year"] == "1993"


def test_contradictory_items_keep_both_values_and_both_titles():
    documents = [{"contradicts": "The Horror Zine", "title": "The Horror Zine (genre magazine directory)",
                  "question": "In which year was The Horror Zine first published?",
                  "original_year": "2009", "altered_year": "2006"}]
    [item] = build_contradictory_items(documents)
    assert item["id"] == "contradictory-01" and item["category"] == "contradictory"
    assert item["answer"] == "2009" and item["conflicting_answer"] == "2006"
    assert item["supporting_titles"] == ["The Horror Zine", "The Horror Zine (genre magazine directory)"]


# The real corpus paragraph. Changing only its year leaves it 0.91 similar (MinHash), above the 0.85 threshold.
ORIGINAL_TEXT = ("Genesis Suite is a 1945 work for narrator, orchestra, and chorus. A musical interpretation of "
                 "the first eleven chapters of the \"Book of Genesis\", the suite was a collaborative work by seven "
                 "composers, some of whom wrote film music in Hollywood. The project was conceived by Nathaniel "
                 "Shilkret, a noted conductor and composer of music for recording, radio and film. Shilkret wrote "
                 "one of the seven pieces and invited the remaining composers to submit contributions as work-for-"
                 "hire. Two giants of western twentieth-century music, Arnold Schoenberg and Igor Stravinsky "
                 "wrote, respectively, the first and last parts. The Biblical text used in the spoken word "
                 "narrative is the American King James Version. It was intended to be a crossover from art music "
                 "to popular music.")
GOOD_DOCUMENT = {"contradicts": "Genesis Suite", "title": "Genesis Suite (concert programme note)",
                 "original_year": "1945", "altered_year": "1947",
                 "text": "Programme note for tonight's performance. The Genesis Suite dates from 1947, an idea of "
                         "conductor Nathaniel Shilkret, with movements by seven composers."}


def test_a_good_conflicting_document_has_no_problems():
    assert find_contradiction_problems([GOOD_DOCUMENT], {"Genesis Suite": ORIGINAL_TEXT}, used_titles=set()) == []


def test_each_broken_rule_is_reported():
    corpus = {"Genesis Suite": ORIGINAL_TEXT}
    near_copy = {**GOOD_DOCUMENT, "text": ORIGINAL_TEXT.replace("1945", "1947")}  # the gotcha: only the year changed
    keeps_original_year = {**GOOD_DOCUMENT, "text": GOOD_DOCUMENT["text"] + " Some say 1945."}
    lacks_altered_year = {**GOOD_DOCUMENT, "text": "Programme note: the Genesis Suite, by seven composers."}
    unknown_original = {**GOOD_DOCUMENT, "contradicts": "No Such Paragraph"}

    assert "near-duplicate" in " ".join(find_contradiction_problems([near_copy], corpus, set()))
    assert "original year 1945" in " ".join(find_contradiction_problems([keeps_original_year], corpus, set()))
    assert "altered year 1947" in " ".join(find_contradiction_problems([lacks_altered_year], corpus, set()))
    assert "not in the corpus" in " ".join(find_contradiction_problems([unknown_original], corpus, set()))
    used_by_eval_set = find_contradiction_problems([GOOD_DOCUMENT], corpus, used_titles={"Genesis Suite"})
    assert "is in the eval set" in " ".join(used_by_eval_set)
