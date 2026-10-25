"""Build data/corpus.jsonl and data/questions.jsonl from the HotpotQA dev set (distractor setting).

Usage (from the repository root):
    .venv/bin/pip install -r eval/requirements.txt
    .venv/bin/python eval/build_dataset.py
"""
import argparse
import json
import sys
from pathlib import Path

import httpx
import pyarrow.parquet as parquet

REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPOSITORY_ROOT / "backend"))  # lets this script import the casefile package

from casefile.datasets.hotpotqa import build_corpus, build_questions  # noqa: E402

# The official CMU download server is often unreachable, so we use the Hugging Face copy linked in the assignment.
HOTPOTQA_DEV_URL = ("https://huggingface.co/api/datasets/hotpotqa/hotpot_qa/parquet/"
                    "distractor/validation/0.parquet")
DOWNLOAD_TIMEOUT_SECONDS = 120


def download_file(url: str, destination: Path) -> None:
    if destination.exists():
        print(f"Using cached {destination}")
        return
    destination.parent.mkdir(parents=True, exist_ok=True)
    print(f"Downloading {url}")
    partial_file = destination.with_suffix(".part")  # never leave a half-written file under the real name
    with httpx.stream("GET", url, timeout=DOWNLOAD_TIMEOUT_SECONDS, follow_redirects=True) as response:
        response.raise_for_status()
        with open(partial_file, "wb") as file:
            for block in response.iter_bytes():
                file.write(block)
    partial_file.rename(destination)


def write_jsonl(records: list[dict], path: Path) -> None:
    with open(path, "w", encoding="utf-8") as file:
        for record in records:
            file.write(json.dumps(record, ensure_ascii=False) + "\n")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--output-dir", type=Path, default=REPOSITORY_ROOT / "data")
    arguments = parser.parse_args()

    raw_file = arguments.output_dir / "raw" / "hotpot_dev_distractor.parquet"
    download_file(HOTPOTQA_DEV_URL, raw_file)
    rows = parquet.read_table(raw_file).to_pylist()

    corpus, report = build_corpus(rows)
    questions = build_questions(rows)
    write_jsonl(corpus, arguments.output_dir / "corpus.jsonl")
    write_jsonl(questions, arguments.output_dir / "questions.jsonl")

    print(f"Questions: {len(questions):,}")
    print(f"Paragraphs: {report.paragraph_slots:,} seen, {report.unique_paragraphs:,} unique")
    print(f"Titles with differing text (first version kept): {len(report.titles_with_different_text)}")


if __name__ == "__main__":
    main()
