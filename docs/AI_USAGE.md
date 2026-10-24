# AI Usage Report

## Tools used
- **Claude Code** (Anthropic Claude models), used in the terminal as a pair programmer: it wrote most of the code
  and tests, and explained each part step by step.
- **grill-me / grilling skills** (Claude Code), used to quiz myself on the design to prepare for the interview.

## How I worked with AI
- **I owned the decisions; AI proposed options.** Before any code, I asked for a written plan (`plan.md`) that
  explains *what* we build, *when* and *why*, and I chose the key technologies myself (see Milestone 1).
- **I required step-by-step explanations.** For every milestone I asked the AI to walk me through what it was doing
  and why, and afterwards to list which files to read and in what order, so I could understand the code.
- **I set the code-readability rules.** I asked for clear, descriptive names (classes as nouns, functions as verbs,
  no abbreviations, named constants), so I can explain and change the code in the interview. All existing code
  was renamed to follow these rules.
- **I controlled the repository.** I reviewed and approved each commit and push, decided how commits are attributed,
  and decided what stays out of the repo (for example, the AI's local instruction file).
- **I verified results myself.** I ran the test suite on my own machine, and when my test command failed with a
  pytest argument error, I fixed how I was invoking it.
- **I tracked the requirements.** I checked progress against the assignment and noticed that the
  "compare 2+ chunking strategies" requirement is only half done (implemented, not yet compared).

## Log by milestone

### Milestone 1: Scaffold and plan
- **I decided:**
  - LLM: Gemini free tier, with Groq as an alternative (free, and allows a model comparison)
  - Dataset: HotpotQA
  - Hosting: Render + Qdrant Cloud
  - UI: React
- **I asked for:** a `plan.md` with goals, milestones, reasons, risks and a requirements checklist before building.
- **AI did:** read the assignment PDF, proposed the architecture and milestone order, created the folder layout,
  `config.py` and `requirements.txt`.

### Milestone 2: Ingestion
- **AI did:**
  - Loaders for 5 formats (PDF, TXT/MD, HTML, JSON/JSONL, CSV)
  - Two chunking strategies (fixed-size and sentence-based)
  - MinHash/LSH near-duplicate detection
  - The ingestion pipeline (add / update / delete)
  - 22 tests
- **I did:**
  - Asked for descriptive naming rules, which led to renaming the whole module.
  - Ran the tests locally (22 passed).
  - Pushed the milestone after reviewing it.
- **Bugs found by tests (fixed by AI):**
  - Chunks spanning two PDF pages were cited with only the first page; chunks now store a `pages` list.
  - The page-marker lookup missed chunks starting exactly at a marker; fixed.

### Milestone 3: Retrieval
- **AI did:**
  - Embedder wrapper (fastembed)
  - Own BM25 sparse encoder
  - Own RRF fusion
  - Own reranker (query coverage + MMR)
  - Qdrant store (dense + sparse vectors, document registry)
  - `HybridSearcher` with three modes (dense / hybrid / hybrid_rerank)
  - 25 new tests (47 total)
- **I did:**
  - Asked for a walkthrough of the milestone and a reading order for understanding it.
  - Reviewed which assignment requirements were complete.
- **Bugs found while testing (fixed by AI):**
  - MMR lambda 0.75 let an 83%-identical chunk beat a different document; lowered to 0.6 (to be tuned in evaluation).
  - Smoke test with the real model: the reranker picked an unrelated document because RRF scores are nearly equal
    (1/61 vs 1/63) and divide-by-max normalisation made all chunks look equally relevant. Switched to min-max
    normalisation and added a regression test. Two unit tests that used unrealistic two-item pools were rewritten
    with realistic RRF-style scores.
- **Limitation found:** min-max normalisation is harsh on very small candidate pools (e.g. a 3-document corpus
  returned an unrelated chunk as the 2nd result). **Fixed by me afterwards**: see "What I changed or verified
  independently" below (`MIN_RELEVANCE` in `rerank.py`, test `test_irrelevant_chunks_are_dropped_instead_of_filling_top_k`).
- **Remaining limitation:** the cutoff is relative to the candidate pool (because of min-max), so a pool where every
  chunk is irrelevant still returns its best one. To be measured on the full dataset in milestone 7.

## What I changed or verified independently
_MMR’s diversity penalty made a totally unrelated chunk look better than a slightly related one, because the reranker always filled every slot; I added a minimum-relevance cutoff before MMR so it returns fewer results instead of junk, and a regression test that failed before the fix and passes after._
