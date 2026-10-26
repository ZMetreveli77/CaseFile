"""Pick candidate paragraphs for the contradictory questions (task H2) and save them for review by hand.

Each candidate has one crisp fact (a single year in its first sentence) and is NOT used by the eval set, so giving it
a conflicting copy later cannot break any existing gold answer. Seeded: the same candidates on every run.

Usage (from the repository root):
    .venv/bin/python eval/pick_contradiction_paragraphs.py
Then read eval/contradiction_candidates.jsonl and keep CONTRADICTION_COUNT of them.
"""
import json
import random
import sys
from pathlib import Path

REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPOSITORY_ROOT / "backend"))  # lets this script import the casefile package

from casefile.evaluation.eval_set import (CANDIDATES_PER_CONTRADICTION, CONTRADICTION_COUNT, EVAL_SEED,  # noqa: E402
                                          find_used_titles, pick_contradiction_paragraphs)

CORPUS_FILE = REPOSITORY_ROOT / "data" / "corpus.jsonl"
EVAL_SET_FILE = REPOSITORY_ROOT / "eval" / "eval_set.jsonl"
CANDIDATES_FILE = REPOSITORY_ROOT / "eval" / "contradiction_candidates.jsonl"
PREVIEW_CHARACTERS = 110


def read_jsonl(path: Path) -> list[dict]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def main() -> None:
    corpus = read_jsonl(CORPUS_FILE)
    used_titles = find_used_titles(read_jsonl(EVAL_SET_FILE))
    # Its own seeded generator, so picking these never changes the questions build_eval_set.py samples.
    random_generator = random.Random(f"{EVAL_SEED}-contradictions")
    candidates = pick_contradiction_paragraphs(corpus, CONTRADICTION_COUNT * CANDIDATES_PER_CONTRADICTION,
                                               random_generator, excluded_titles=used_titles)

    lines = [json.dumps(candidate, ensure_ascii=False) + "\n" for candidate in candidates]
    CANDIDATES_FILE.write_text("".join(lines), encoding="utf-8")
    print(f"Skipped {len(used_titles)} paragraphs the eval set uses. {len(candidates)} candidates:\n")
    for number, candidate in enumerate(candidates, start=1):
        preview = candidate["fact_sentence"][:PREVIEW_CHARACTERS]
        print(f"{number:2}. [{candidate['year']}] {candidate['title']}: {preview}")
    print(f"\nSaved to {CANDIDATES_FILE.relative_to(REPOSITORY_ROOT)}. Keep {CONTRADICTION_COUNT} after review.")


if __name__ == "__main__":
    main()