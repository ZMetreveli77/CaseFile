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
- **Code-review follow-up (AI):** after I ran `/code-review` on my reranker fix, the AI fixed the issues in its own
  milestone-3 code:
  - `rerank_results` no longer modifies its input and keeps the fused score in `details["fused_score"]`
  - `HybridSearcher` now passes `mmr_lambda` through (it also passed `min_relevance`, which my v2 later removed)
  - inner functions renamed to verbs; rounding uses a named constant
  - 2 new tests
- **Limitation found:** min-max normalisation is harsh on very small candidate pools (e.g. a 3-document corpus
  returned an unrelated chunk as the 2nd result). **Fixed by me afterwards** (v1, then v2): see
  "What I changed or verified independently" below.
- **Remaining limitation:** see the v2 trade-off below.

### Milestone 4: Dataset + indexing
- **I decided:** to use the **whole HotpotQA dev set** (66,581 unique paragraphs, all 7,405 questions usable for
  evaluation) instead of a sampled subset. The full official split already exceeds the 50k requirement, so no sampling
  is needed and every question stays answerable from the corpus.
- **AI did:**
  - Found the official CMU download server unreachable and switched to the Hugging Face copy (linked in the assignment).
  - Worked around missing SSL certificates in the macOS Python by using `httpx`.
  - Wrote `casefile/datasets/hotpotqa.py` (rows → corpus + questions; one paragraph per Wikipedia title) and
    `eval/build_dataset.py` (download + write `data/corpus.jsonl`, `data/questions.jsonl`).
  - Added a **batched ingestion path**: 3 store calls per batch of 256 documents instead of 3 per document
    (about 5.5 hours of network round trips down to about a minute). Re-runs are resumable.
  - Wrote `eval/index_corpus.py` and 4 new tests (55 total).
- **I set up** the Qdrant Cloud cluster (AWS Frankfurt, close to the planned Render region) and the git-ignored `.env`.
- **I measured `AVERAGE_CHUNK_TOKENS`** (see "What I changed or verified independently").
- **Measured:** embedding is about 95% of indexing time (about 30 chunks/s on an Apple M4 CPU). MinHash dedup adds
  about 2 minutes; chunking and BM25 are negligible.
- **Full indexing run:**
  - 66,555 documents added, 26 duplicate documents skipped, **78,730 chunks** in Qdrant Cloud.
  - Took 60 min 32 s; the cloud uploads made it slower than the ~40 min estimate.
  - Meets the 50,000-record requirement.
- **I wrote and ran the retrieval spot check, and wrote the dataset tests** (see "What I changed or verified
  independently").

### Milestone 5: Agentic RAG (in progress)
- **AI did:**
  - Found that `gemini-2.5-flash` is no longer offered to new keys, and that the `google-genai` SDK pinned in
    milestone 1 (0.5.0) was too old to even list models. Upgraded it to 2.33.0, which also needed pydantic 2.14.1.
  - Tested current models with a real tool call. `gemini-3.8-flash` / `3.7-flash` worked but took 166–245 s under
    free-tier load (503/504 errors at other times). `gemini-3.5-flash-lite` answered in 0.9 s, so it became the default
    (`GEMINI_MODEL` in `.env` switches it). A background test without a timeout hung, so every request now has a
    30 s timeout.
  - Wrote:
    - `rag/llm.py`: provider-neutral message types, `GeminiProvider`, and the error translation
      (429/500/502/503/504 and network timeouts → `RetryableLLMError`, others → `LLMError`).
    - `rag/tools.py`: `search_documents` / `read_document`, plus a per-question evidence log.
    - `rag/agent.py`: the multi-step loop, the step limit, JSON answer parsing, and abstaining on an invalid format.
    - The `rag/prompts.py` skeleton.
    - Tests with a scripted fake LLM: `test_agent.py`, `test_tools.py`, `test_llm.py`.
  - Caught its own bug: `read_document` logged truncated passages as evidence, so the LLM could have cited text it
    never saw.
- **I am writing:** the retry logic (`rag/retry.py`, task U6), the citation validator (U2) and the grounding rules (U1).

## What I changed or verified independently

### Reranker fix v1: minimum-relevance cutoff
MMR's diversity penalty made a totally unrelated chunk look better than a slightly related one, because the
reranker always filled every slot. I added a minimum-relevance cutoff (`MIN_RELEVANCE = 0.05`) before MMR, so it
returns fewer results instead of junk. I also added the regression test
`test_irrelevant_chunks_are_dropped_instead_of_filling_top_k`.

### Code review of my v1
I ran `/code-review` on my fix. It found that my cutoff was applied to a **pool-relative** (min-max) score, so
whether a chunk was dropped depended on the other candidates, not on the chunk itself:
- A relevant chunk that came **last** in a small pool always got normalised score 0 and was dropped.
- When all candidates had the **same** score, every chunk got normalised score 1, so the cutoff never dropped anything.

Both cases were reproduced with small scripts before changing anything.

### Reranker fix v2: absolute signals
I replaced the cutoff with `is_junk()` in `rerank.py`. A candidate is junk only if:
- **none of the query's words** appear in it (coverage == 0), **and**
- semantic search did **not** rank it in its top `DENSE_RANK_LIMIT` (10).

The single best candidate is always kept, so the LLM still sees the best evidence and can decide to abstain.
I removed `MIN_RELEVANCE` (also from `HybridSearcher`) and deleted the test for it, since the setting no longer exists.

- **AI help for v2:** I wrote the code and tests in my editor. I used Claude Code's hints, its review feedback,
  and code suggestions from earlier messages in the same session. No other AI tool was used.

- **Tests I wrote:**
  - `test_relevant_chunk_is_kept`: a near-tied relevant chunk that is last in the pool is kept
  - `test_tied_pool_of_irrelevant_chunks_is_filtered`: a tied pool of irrelevant chunks is filtered
- **Test I updated:** `test_close_rrf_scores_do_not_let_diversity_pick_an_unrelated_chunk`. Its candidates now
  carry `dense_rank` values, because in the real pipeline every chunk found by semantic search has one.
- **Verified:** all tests pass. Both review scenarios behave correctly. A real-model run (fastembed) still answers
  "why did payments stop working?" with `incident.txt`, then `changes.txt`.
- **Trade-off (known limitation):** when the corpus is smaller than `DENSE_RANK_LIMIT`, every chunk is in the
  dense top 10, so `is_junk` never fires. In the 3-document smoke test, "CHG-43" again returns `offsite.txt`
  as the 2nd result. On the 50k-paragraph corpus, being in the dense top 10 is a meaningful signal.
  `DENSE_RANK_LIMIT` will be tuned in the evaluation (milestone 7).

### Measured AVERAGE_CHUNK_TOKENS for BM25 (milestone 4)
`AVERAGE_CHUNK_TOKENS` in `bm25.py` was a guess (120). BM25 weights are computed when chunks are stored, so the value
had to be right **before** indexing the 78,828 chunks. I wrote `eval/measure_chunk_tokens.py`. It chunks the corpus
with the same settings as the indexer (read from `get_settings()`, so the two can't drift apart) and counts tokens with
the same `tokenize` BM25 uses.

- **Result:** mean **53.3** tokens per chunk (median 53, min 2, max 186; 78,828 chunks, 472 characters on average).
  I set `AVERAGE_CHUNK_TOKENS = 53`. The old guess of 120 would have made every chunk look short and
  under-penalised long ones.
- **AI help:** Claude Code suggested the task and gave hints. Its code review caught a first value (87) that
  didn't match the corpus, plus a missing import path and a missing argument default. I fixed the script myself.

### Tests for the dataset builder (milestone 4)
I wrote `backend/tests/test_hotpotqa.py`: 6 tests on small fake HotpotQA rows (no download needed). They cover:
- sentence joining
- one paragraph per title
- first version kept, with differences reported once
- stable order (reproducibility)
- unique, ordered supporting titles
- every supporting title present in the corpus

- **Verified:**
  - Breaking `join_sentences` on purpose makes 2 of the tests fail, so they catch real bugs.
  - On the real data, all 7,405 questions have every supporting paragraph in the corpus (0 missing).
- **AI help:** Claude Code proposed the list of tests and the `make_row` shape. I wrote the tests.

### Retrieval spot check (milestone 4)
I wrote `eval/spot_check.py`. It takes the first 3 *bridge* and the first 2 *comparison* questions from
`data/questions.jsonl` (a fixed, reproducible choice), runs each through all three search modes (`dense`, `hybrid`,
`hybrid_rerank`), and reports the rank of each supporting paragraph in the top 8.

- **Results** (supporting paragraphs found in the top 8):

  | Mode | Partial corpus (about 27% indexed) | **Full corpus (78,730 chunks)** |
  |---|---|---|
  | dense | 7/10 | **7/10** |
  | hybrid | 8/10 | **7/10** |
  | hybrid_rerank | 8/10 | **6/10** |

  The partial run was optimistic: fewer indexed paragraphs means fewer distractors competing for the top 8.
- **Findings (full corpus):**
  - **Bridge second hops are never found.** In all three bridge questions the second paragraph is missed in every
    mode ("Shirley Temple", "The Hork-Bajir Chronicles", "Adriana Trigiani"). The question never names that entity:
    "the woman who portrayed Corliss Archer in the film Kiss and Tell" only leads to "Shirley Temple" after reading the
    "Kiss and Tell" paragraph, so one search can't find it. This is the case for the multi-step agent planned for
    milestone 5: search, read, then search again for the bridge entity.
  - **The reranker penalises paraphrases.** In `hybrid_rerank`, the correct "Ed Wood" paragraph (dense rank 2) fell
    to rank 10, behind the irrelevant "Woodson, Arkansas". Why:
    1. The paragraph says "Edward Davis Wood Jr.", never "Ed".
    2. BM25 didn't return it at all, so it got only the dense half of the RRF score.
    3. Its exact-word query coverage was only 1/6.

    The reranker's relevance (70% fused score + 30% exact-word coverage) therefore ranked it below a place name that
    shares more query words. MMR was not the cause: the word overlap with "Ed Wood (film)" is only 7%.
  - Comparison questions did better (4/4 paragraphs found in dense and hybrid, 3/4 in hybrid_rerank because of the
    "Ed Wood" drop), because both entities are named in the question.
  - **Decision:** not to tune the reranker on 5 questions (that would be overfitting). `COVERAGE_WEIGHT` and the dense
    weight will be tuned in the milestone 7 evaluation on 40+ questions.
- **AI help:** Claude Code defined the task (what to measure, the three-mode comparison), reviewed the script, and
  ran it on the partial and the full corpus. It also diagnosed the "Ed Wood" drop by printing each candidate's
  ranks, coverage and relevance. Claude Code wrote this entry at my request, from the run output, to keep the
  description neutral.
