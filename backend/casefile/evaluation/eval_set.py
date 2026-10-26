"""The fixed evaluation question set: which questions, which categories, and the dev/test split.

Everything is seeded, so building the set twice gives the same questions in the same order. Settings are tuned on the
"dev" half only and final numbers are reported on "test", so we never grade ourselves on what we tuned for.
"""
import random
import re

from casefile.ingestion.dedup import DuplicateDetector

EVAL_SEED = 2026
BRIDGE_COUNT = 20  # multi-hop: find one fact, then use it to find the next
COMPARISON_COUNT = 10  # multi-hop: two named entities compared
SIMPLE_COUNT = 10  # one paragraph is enough (generated once from a single paragraph, then checked by hand)
SPOT_CHECK_FIRST_PER_TYPE = {"bridge": 3, "comparison": 2}  # used in eval/spot_check.py: kept out of the set
SIMPLE_PARAGRAPH_CHARACTERS = (300, 800)  # long enough to hold a fact, short enough to be one chunk
CONTRADICTION_COUNT = 10  # paragraphs that get a conflicting copy (task H2)
CANDIDATES_PER_CONTRADICTION = 3  # pick more than needed: a person still chooses the final ones by hand
YEAR_PATTERN = re.compile(r"\b(1[5-9]\d{2}|20[0-2]\d)\b")  # 1500-2029, as a whole word ("1902", not "19021")
GLUED_NUMBERS = re.compile(r"\d{5,}")  # e.g. "(17 January 189912 January 1960)": a hidden second year, so skip it
FIRST_SENTENCE_END = re.compile(r"(?<=[.!?])\s+")  # a sentence ends with . ! or ? followed by whitespace
# Paragraphs the false-premise questions rely on: they must keep NOT supporting the false claim, so don't touch them.
FALSE_PREMISE_TITLES = frozenset({"Shirley Temple", "Animorphs", "Adriana Trigiani", "Ed Wood"})

# Questions the corpus cannot answer. Three kinds, so abstention is tested on more than obviously silly questions.
UNANSWERABLE_QUESTIONS = [
    {"question": "Who won the 2030 FIFA World Cup?", "kind": "future event"},
    {"question": "Which film won the Academy Award for Best Picture in 2029?", "kind": "future event"},
    {"question": "Who was elected President of France in 2032?", "kind": "future event"},
    {"question": "In which year did the city of Zorvania host the Winter Olympics?", "kind": "fictional entity"},
    {"question": "Who founded the Kestrelmoor Institute of Applied Linguistics?", "kind": "fictional entity"},
    {"question": "What is the population of the Brennholt archipelago?", "kind": "fictional entity"},
    {"question": "In which year did Shirley Temple win the Nobel Prize in Physics?", "kind": "false premise"},
    {"question": "Which Animorphs book was adapted into a film directed by Adriana Trigiani?", "kind": "false premise"},
    {"question": "How many goals did Ed Wood score for the United States national football team?", "kind": "false premise"},
    {"question": "What is the CaseFile project's API key?", "kind": "out of scope"},
]


def find_spot_check_ids(questions: list[dict]) -> set[str]:
    """The questions eval/spot_check.py used (first N per type, in file order)."""
    picked, count_by_type = set(), {question_type: 0 for question_type in SPOT_CHECK_FIRST_PER_TYPE}
    for question in questions:
        question_type = question["type"]
        if count_by_type.get(question_type, 0) < SPOT_CHECK_FIRST_PER_TYPE.get(question_type, 0):
            picked.add(question["id"])
            count_by_type[question_type] += 1
    return picked


def sample_hotpot_questions(questions: list[dict], random_generator: random.Random) -> list[dict]:
    """Seeded sample of bridge and comparison questions, excluding the spot-check ones."""
    excluded_ids = find_spot_check_ids(questions)
    sampled = []
    for question_type, count in (("bridge", BRIDGE_COUNT), ("comparison", COMPARISON_COUNT)):
        pool = [question for question in questions if question["type"] == question_type and question["id"] not in excluded_ids]
        for question in random_generator.sample(pool, count):
            sampled.append({"id": question["id"], "category": question_type, "question": question["question"],
                            "answer": question["answer"], "supporting_titles": question["supporting_titles"],
                            "source": "hotpotqa"})
    return sampled


def pick_simple_paragraphs(corpus: list[dict], count: int, random_generator: random.Random,
                           excluded_titles: set[str]) -> list[dict]:
    """Seeded choice of single paragraphs to generate one-hop questions from."""
    shortest, longest = SIMPLE_PARAGRAPH_CHARACTERS
    pool = [paragraph for paragraph in corpus
            if shortest <= len(paragraph["text"]) <= longest and paragraph["title"] not in excluded_titles]
    return random_generator.sample(pool, count)


def build_unanswerable_items() -> list[dict]:
    return [{"id": f"unanswerable-{number:02d}", "category": "unanswerable", "question": item["question"],
             "answer": None, "supporting_titles": [], "source": f"hand-written ({item['kind']})"}
            for number, item in enumerate(UNANSWERABLE_QUESTIONS, start=1)]


def assign_splits(items: list[dict], random_generator: random.Random) -> list[dict]:
    """Within each category, shuffle (seeded) and give half to "dev" and half to "test"."""
    for category in sorted({item["category"] for item in items}):
        category_items = [item for item in items if item["category"] == category]
        random_generator.shuffle(category_items)
        for position, item in enumerate(category_items):
            item["split"] = "dev" if position < len(category_items) // 2 else "test"
    return items


def find_used_titles(eval_items: list[dict]) -> set[str]:
    """Every paragraph the eval set depends on: its supporting titles plus the false-premise paragraphs.
    Altering any of these would silently break a gold answer (or make a false premise true)."""
    used_titles = {title for item in eval_items for title in item["supporting_titles"]}
    return used_titles | FALSE_PREMISE_TITLES


def find_single_year_fact(text: str) -> tuple[str, str] | None:
    """(year, first sentence) if the paragraph has exactly ONE distinct year and it is in the first sentence.

    One year only: then "the year" is unambiguous, and a conflicting copy changes exactly that fact. Digits glued
    together (a corpus extraction bug, "189912 January 1960") can hide a second year, so those paragraphs are skipped.
    First sentence: that is where Wikipedia states the paragraph's main fact (founded, born, released ...).
    """
    distinct_years = set(YEAR_PATTERN.findall(text))
    if len(distinct_years) != 1 or GLUED_NUMBERS.search(text):
        return None
    [year] = distinct_years
    first_sentence = FIRST_SENTENCE_END.split(text, maxsplit=1)[0]
    return (year, first_sentence) if year in first_sentence else None


def pick_contradiction_paragraphs(corpus: list[dict], count: int, random_generator: random.Random,
                                  excluded_titles: set[str]) -> list[dict]:
    """Seeded choice of paragraphs with one crisp year fact, never one the eval set already uses.

    Also skipped: lists ("List of ...") and titles that contain the year themselves ("Kaadu (1952 film)"), because
    changing the year in the text would then conflict with the title too.
    """
    shortest, longest = SIMPLE_PARAGRAPH_CHARACTERS
    pool = []
    for paragraph in corpus:
        title, text = paragraph["title"], paragraph["text"]
        is_usable = (title not in excluded_titles and shortest <= len(text) <= longest
                     and not title.startswith("List of") and not YEAR_PATTERN.search(title))
        year_fact = find_single_year_fact(text) if is_usable else None
        if year_fact is not None:
            year, first_sentence = year_fact
            pool.append({"title": title, "year": year, "fact_sentence": first_sentence, "text": text})
    return random_generator.sample(pool, count)


def build_contradictory_items(conflicting_documents: list[dict]) -> list[dict]:
    """One eval item per conflicting document: the gold answer is the ORIGINAL value, the altered one is kept too.

    Both titles are supporting: a good answer finds both sources and reports that they disagree (grounding rule 5).
    """
    return [{"id": f"contradictory-{number:02d}", "category": "contradictory", "question": document["question"],
             "answer": document["original_year"], "conflicting_answer": document["altered_year"],
             "supporting_titles": [document["contradicts"], document["title"]],
             "source": "hand-written conflicting document"}
            for number, document in enumerate(conflicting_documents, start=1)]


def contains_year(text: str, year: str) -> bool:
    """True if `year` appears as a whole word ("1849" in "in 1849.", but not inside "18490")."""
    return re.search(rf"\b{re.escape(year)}\b", text) is not None


def find_contradiction_problems(conflicting_documents: list[dict], corpus_text_by_title: dict[str, str],
                                used_titles: set[str]) -> list[str]:
    """Check the hand-written conflicting documents; returns one message per problem (empty list = all good).

    These are the checks first done by hand, so a later edit to a document can't silently break the test set.
    """
    problems = []
    for document in conflicting_documents:
        original_title, new_title, text = document["contradicts"], document["title"], document["text"]
        document_label = repr(new_title)
        if original_title not in corpus_text_by_title:
            problems.append(f"{document_label}: the original paragraph {original_title!r} is not in the corpus")
            continue
        if original_title in used_titles:
            problems.append(f"{document_label}: {original_title!r} is in the eval set, so a gold answer would break")
        if new_title in corpus_text_by_title:
            problems.append(f"{document_label}: a corpus paragraph already has this title, so uploads would mix them")
        if not contains_year(text, document["altered_year"]):
            problems.append(f"{document_label}: the altered year {document['altered_year']} is not in the text")
        if contains_year(text, document["original_year"]):
            problems.append(f"{document_label}: the original year {document['original_year']} is still in the text")
        duplicate_detector = DuplicateDetector()
        duplicate_detector.add(original_title, corpus_text_by_title[original_title])
        if duplicate_detector.find_duplicate(text) is not None:
            problems.append(f"{document_label}: near-duplicate of {original_title!r}, so ingestion would skip it")
    return problems
