# CaseFile: notes for Claude

See `plan.md` for goals, milestones and decisions. Log AI contributions in `docs/AI_USAGE.md` after each milestone.
Commits: no `Co-Authored-By` line. Don't push without asking.

## Run tests
`cd backend && ../.venv/bin/python -m pytest -q`

## Naming rules
The author must explain this code in an interview, so names must be self-explanatory.
- Classes are nouns that say what the thing is: `DocumentLoader`, `DuplicateDetector`, `HybridSearcher`.
- Functions are verbs that say what they do: `load_pdf_file`, `split_by_sentences`, `find_duplicate`.
- Variables use full words, not abbreviations: `chunk_text`, not `t`; `duplicate_chunk_id`, not `dup`.
- True/false values read like a question: `is_duplicate`, `has_enough_evidence`, `should_abstain`.
- Fixed numbers get a named constant: `MAX_CHUNK_CHARACTERS = 800`, not a bare `800`.
- Technical terms (MinHash, LSH, RRF, BM25) stay in names, with a one-line comment explaining them.
