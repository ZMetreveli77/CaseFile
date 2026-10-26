"""Build the contradictory questions (task H2) as eval/contradictory_set.jsonl, split 5 dev / 5 test with a fixed seed.

Reads eval/contradictions_written.jsonl (one hand-written conflicting document + question per fact). Writes its own
file instead of eval/eval_set.jsonl, because eval/build_eval_set.py rewrites that file from scratch and would drop
these questions. eval/run_answer_eval.py loads both files. Safe to re-run: the output is replaced, never appended.

Usage (from the repository root):
    .venv/bin/python eval/add_contradictory_questions.py
"""
import json
import random
import sys
from collections import Counter
from pathlib import Path

REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPOSITORY_ROOT / "backend"))  # lets this script import the casefile package

from casefile.evaluation.eval_set import EVAL_SEED, assign_splits, build_contradictory_items  # noqa: E402

CONFLICTING_DOCUMENTS_FILE = REPOSITORY_ROOT / "eval" / "contradictions_written.jsonl"
CONTRADICTORY_SET_FILE = REPOSITORY_ROOT / "eval" / "contradictory_set.jsonl"
CONTRADICTORY_CATEGORY = "contradictory"


def read_jsonl(path: Path) -> list[dict]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def write_jsonl(records: list[dict], path: Path) -> None:
    path.write_text("".join(json.dumps(record, ensure_ascii=False) + "\n" for record in records), encoding="utf-8")


def main() -> None:
    contradictory_items = build_contradictory_items(read_jsonl(CONFLICTING_DOCUMENTS_FILE))
    # Own seeded generator: the split is the same on every run and doesn't depend on the other categories.
    assign_splits(contradictory_items, random.Random(f"{EVAL_SEED}-{CONTRADICTORY_CATEGORY}"))
    write_jsonl(contradictory_items, CONTRADICTORY_SET_FILE)

    print(f"Wrote {len(contradictory_items)} contradictory questions to "
          f"{CONTRADICTORY_SET_FILE.relative_to(REPOSITORY_ROOT)}")
    print(f"Split: {dict(Counter(item['split'] for item in contradictory_items))}")
    for item in contradictory_items:
        print(f"  {item['id']} [{item['split']}] {item['answer']} vs {item['conflicting_answer']}: {item['question']}")


if __name__ == "__main__":
    main()
