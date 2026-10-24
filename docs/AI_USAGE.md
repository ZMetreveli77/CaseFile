# AI Usage Report

Tools used: Claude Code (Anthropic Claude models), used in the terminal as a pair programmer.

## Log by milestone

### Milestone 1: Scaffold
- **AI did:** read the assignment PDF, proposed the architecture and the milestone plan (`plan.md`), and created the folder layout, `config.py` and `requirements.txt`.
- **I decided:** LLM provider (Gemini free tier), dataset (HotpotQA), hosting (Render + Qdrant Cloud), UI (React).
- **I changed / verified:** _(fill in)_

### Milestone 2: Ingestion
- **AI did:** wrote the loaders (PDF, TXT/MD, HTML, JSON/JSONL, CSV), two chunking strategies, MinHash/LSH dedup, the ingestion pipeline and 22 tests.
- **Bugs found while testing:** chunks spanning two PDF pages were cited with only the first page. Fixed by storing a `pages` list, and the page-marker lookup was also fixed for chunks that start exactly at a marker.
- **I changed / verified:** _(fill in)_

### Milestone 3: Retrieval
- **AI did:** wrote the embedder wrapper (fastembed), own BM25 sparse encoder, own RRF fusion, own reranker
  (query coverage + MMR), the Qdrant store (dense + sparse vectors, document registry), `HybridSearcher`
  with three modes (dense / hybrid / hybrid_rerank), and 25 new tests (47 total).
- **Bugs found while testing:**
  - MMR lambda 0.75 let an 83%-identical chunk beat a different document; lowered to 0.6 (to be tuned in evaluation).
  - Smoke test with the real model: the reranker picked an unrelated document because RRF scores are nearly equal
    (1/61 vs 1/63) and divide-by-max normalisation made all chunks look equally relevant. Switched to min-max
    normalisation and added a regression test. Two unit tests that used unrealistic two-item pools were rewritten
    with realistic RRF-style scores.
- **Known limitation:** min-max normalisation is harsh on very small candidate pools (e.g. a 3-document corpus can
  return an unrelated chunk as the 2nd result). To be measured on the full dataset in milestone 7.
- **I changed / verified:** _(fill in)_
