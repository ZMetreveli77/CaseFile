from casefile.datasets.hotpotqa import build_corpus, build_question, build_questions, join_sentences

PARIS = ("Paris", ["Paris is the capital of France.", " It is on the Seine."])
BERLIN = ("Berlin", ["Berlin is the capital of Germany."])
ROME = ("Rome", ["Rome is the capital of Italy."])


def make_row(question_id, titles_and_sentences, supporting):
    """Build a fake HotpotQA row with the same shape as the real data.

    titles_and_sentences: [("Paris", ["Paris is in France.", " It is big."]), ...]
    supporting: [("Paris", 0), ...]  -> (title, sentence index)
    """
    return {
        "id": question_id,
        "question": f"Question {question_id}?",
        "answer": "answer",
        "type": "bridge",
        "level": "hard",
        "context": {
            "title": [title for title, sentences in titles_and_sentences],
            "sentences": [sentences for title, sentences in titles_and_sentences],
        },
        "supporting_facts": {
            "title": [title for title, sentence_index in supporting],
            "sent_id": [sentence_index for title, sentence_index in supporting],
        },
    }


def test_join_sentences_keeps_single_spaces():
    assert join_sentences(["A b.", " C d."]) == "A b. C d."
    assert join_sentences([" A b.", " C d."]) == "A b. C d."  # leading space of the first sentence is stripped


def test_corpus_keeps_one_paragraph_per_title():
    rows = [
        make_row("q1", [PARIS, BERLIN], [("Paris", 0)]),
        make_row("q2", [PARIS, ROME], [("Rome", 0)]),
    ]
    corpus, report = build_corpus(rows)
    assert len(corpus) == 3  # Paris, Berlin, Rome: Paris only once
    assert report.paragraph_slots == 4  # every paragraph seen, duplicates included
    assert report.unique_paragraphs == 3


def test_first_version_kept_and_differences_reported():
    other_paris_text = ("Paris", ["Paris is a city in France."])
    rows = [
        make_row("q1", [PARIS], [("Paris", 0)]),
        make_row("q2", [other_paris_text], [("Paris", 0)]),
        make_row("q3", [other_paris_text], [("Paris", 0)]),
    ]
    corpus, report = build_corpus(rows)
    assert corpus[0]["text"] == "Paris is the capital of France. It is on the Seine."  # first version kept
    assert report.titles_with_different_text == ["Paris"]  # reported once, not once per extra row


def test_corpus_order_is_stable():
    rows = [
        make_row("q1", [PARIS, BERLIN], [("Paris", 0)]),
        make_row("q2", [ROME, PARIS], [("Rome", 0)]),
    ]
    first_corpus, _ = build_corpus(rows)
    second_corpus, _ = build_corpus(rows)
    assert first_corpus == second_corpus
    assert [record["title"] for record in first_corpus] == ["Paris", "Berlin", "Rome"]  # first-seen order


def test_question_supporting_titles_are_unique_and_ordered():
    row = make_row("q1", [("A", ["a0.", " a1."]), ("B", ["b0.", " b1.", " b2."])],
                   [("B", 0), ("A", 1), ("B", 2)])
    question = build_question(row)
    assert question["supporting_titles"] == ["B", "A"]
    assert len(question["supporting_facts"]) == 3  # every fact is still kept


def test_every_supporting_title_is_in_the_corpus():
    rows = [
        make_row("q1", [PARIS, BERLIN], [("Paris", 0), ("Berlin", 0)]),
        make_row("q2", [ROME, PARIS], [("Rome", 0), ("Paris", 1)]),
    ]
    corpus, _ = build_corpus(rows)
    corpus_titles = {record["title"] for record in corpus}
    for question in build_questions(rows):
        missing_titles = set(question["supporting_titles"]) - corpus_titles
        assert not missing_titles, f"{question['id']} needs {missing_titles}, which are not in the corpus"