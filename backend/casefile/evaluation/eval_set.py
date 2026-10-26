"""The fixed evaluation question set: which questions, which categories, and the dev/test split.

Everything is seeded, so building the set twice gives the same questions in the same order. Settings are tuned on the
"dev" half only and final numbers are reported on "test", so we never grade ourselves on what we tuned for.
"""
import random

EVAL_SEED = 2026
BRIDGE_COUNT = 20  # multi-hop: find one fact, then use it to find the next
COMPARISON_COUNT = 10  # multi-hop: two named entities compared
SIMPLE_COUNT = 10  # one paragraph is enough (generated once from a single paragraph, then checked by hand)
SPOT_CHECK_FIRST_PER_TYPE = {"bridge": 3, "comparison": 2}  # used in eval/spot_check.py: kept out of the set
SIMPLE_PARAGRAPH_CHARACTERS = (300, 800)  # long enough to hold a fact, short enough to be one chunk

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
