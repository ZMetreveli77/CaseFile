# Product

<!-- impeccable:product-schema 1 -->

## Platform

web

## Users
Designed as a working tool for an investigative analyst (journalist, auditor, researcher) who has to dig across
many documents, connect facts from different sources, and trust only what the evidence supports.

The live demo is also judged by Talent Growth Program reviewers. They upload a few files, ask hard questions
(multi-hop, unanswerable, contradictory), and check the engine's rigor. Without hunting for it, they must be able
to see how an answer was reached: the search steps, the source chunks and their scores.

## Product Purpose
CaseFile is an AI investigation engine that cites its evidence. It ingests documents (PDF, TXT/MD, HTML,
JSON/JSONL, CSV), searches them with hybrid retrieval (dense + own BM25, RRF fusion, reranker), and answers with
an agent that plans multi-step searches. Answers are tied to source chunks, contradictions between sources are
reported, and it abstains when the evidence is insufficient.

Success: a user can see why an answer is trustworthy (or why CaseFile refused) in one pass. A reviewer comes
away convinced this is an investigation engine, not "chat with PDF".

## Positioning
**It shows its reasoning.** The agent's investigation is visible as it happens: the question it started from,
each tool call (`search_documents`, document lookups), which documents each step returned, and how those
became cited claims. A chat-with-PDF tool hides this. In CaseFile the process is the product.

## Operating Context
- Workflow: upload/manage documents → ask a question → watch the investigation stream → read the answer → open
  the cited source chunks.
- Backend API (FastAPI): `POST/GET/PUT/DELETE /documents`, `GET /sources/{chunk_id}`, `POST /ask`,
  `POST /ask/stream` (Server-Sent Events: `started`, `tool_call`, `tool_result`, …, final answer),
  `GET /formats` (allowed extensions, max upload size).
- Answer shape: answer text, claims with citations, conflicts (description + citations), `should_abstain` and
  `abstain_reason`, notes.
- Corpus: about 66.5k HotpotQA paragraphs (78.7k chunks) in Qdrant Cloud, plus user-uploaded files.

## Capabilities and Constraints
- Frontend: React (Vite + TypeScript), built and served by the FastAPI app as one deployable service (milestone 8,
  not yet built).
- Hosting: Render free tier + Qdrant Cloud free tier. Cold starts and slow first responses are normal and must be
  handled gracefully in the UI (clear waiting states, no dead-looking screens).
- LLM: Gemini free tier with Groq as an alternative. Rate limits and quota errors happen and must surface as
  understandable states, not crashes.
- **Code must stay simple.** The author explains and changes the frontend live in an interview without AI, so it
  has minimal dependencies and plain, readable components. It follows the repo naming rules in `CLAUDE.md`:
  noun components, verb functions, full-word variables, question-style booleans, named constants.
- Required by the assignment: citations, contradiction reporting, abstention, upload/manage/ask/view-sources UI.
- Undecided: language support beyond English, a formal accessibility standard.

## Brand Commitments
- Name: **CaseFile**. Tagline in the README: "an AI investigation engine that cites its evidence."
- Look (chosen 2026-10-27 after three direction rounds): the familiar research-assistant layout, executed
  cleanly, not a themed visual world. Light and dark are both first-class (follow the system setting, plus a
  toggle). A few colours, each with one meaning (cited, conflict, not cited / declined), never decoration.
  The investigation steps stay visible above the answer.

## Evidence on Hand
- Evaluation report: `docs/EVALUATION.md` (60 questions; Recall@K, MRR, answer correctness, citation accuracy,
  config comparison, error analysis). Results in `eval/results/`.
- AI usage report: `docs/AI_USAGE.md`. Assignment brief: `docs/task/assignment.pdf`.
- No users, testimonials or production metrics exist. Don't invent any. Cite numbers only from the eval
  report.

## Product Principles
1. **Process is visible.** Every answer can be traced back through the steps and sources that produced it.
2. **Evidence before prose.** A claim without a viewable source doesn't belong on screen.
3. **Honest outcomes are first-class.** Abstentions, conflicts, slow starts and quota errors are designed states,
   not errors to hide.
4. **Explainable code beats clever code.** If the author can't explain a UI choice live, it doesn't go in.
