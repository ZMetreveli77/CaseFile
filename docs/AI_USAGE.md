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
