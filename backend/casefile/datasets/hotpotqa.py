"""Turn HotpotQA rows into a paragraph corpus and an evaluation question set.

Each HotpotQA row is one question with 10 Wikipedia paragraphs ("context"): 2 support the answer, 8 are distractors.
The same Wikipedia paragraph appears under many questions, so the corpus keeps one copy per title.
The paragraph id is the Wikipedia title, because `supporting_facts` refers to paragraphs by title.
"""
from dataclasses import dataclass, field


@dataclass
class CorpusBuildReport:
    paragraph_slots: int = 0  # paragraphs seen across all questions, duplicates included
    unique_paragraphs: int = 0
    titles_with_different_text: list[str] = field(default_factory=list)  # same title, slightly different text


def join_sentences(sentences: list[str]) -> str:
    # HotpotQA sentences already carry their leading space (" The film ..."), so join without a separator.
    return "".join(sentences).strip()


def build_corpus(rows: list[dict]) -> tuple[list[dict], CorpusBuildReport]:
    """One record per unique title, in first-seen order (so the output is the same on every run)."""
    report = CorpusBuildReport()
    text_by_title: dict[str, str] = {}
    for row in rows:
        context = row["context"]
        for title, sentences in zip(context["title"], context["sentences"]):
            report.paragraph_slots += 1
            text = join_sentences(sentences)
            if title not in text_by_title:
                text_by_title[title] = text
            elif text_by_title[title] != text and title not in report.titles_with_different_text:
                report.titles_with_different_text.append(title)
    report.unique_paragraphs = len(text_by_title)
    corpus = [{"id": title, "title": title, "text": text} for title, text in text_by_title.items()]
    return corpus, report


def build_question(row: dict) -> dict:
    facts = row["supporting_facts"]
    supporting_titles = list(dict.fromkeys(facts["title"]))  # unique, original order
    return {
        "id": row["id"],
        "question": row["question"],
        "answer": row["answer"],
        "type": row["type"],  # "bridge" (chain two facts) or "comparison"
        "level": row["level"],
        "supporting_titles": supporting_titles,
        "supporting_facts": [{"title": title, "sentence_index": sentence_index}
                             for title, sentence_index in zip(facts["title"], facts["sent_id"])],
    }


def build_questions(rows: list[dict]) -> list[dict]:
    return [build_question(row) for row in rows]
