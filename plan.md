# CaseFile Plan: what, when, why

## 1. Goal (why this project exists)
Talent Growth Program assignment (`docs/task/assignment.pdf`): build an **AI investigation engine**. It must find
information across many documents, connect facts from different sources, give cited answers, point out
contradictions, and refuse to answer when the evidence is missing. It must not be a simple "chat with PDF".

Deliverables: GitHub repo, live demo URL, README, Evaluation Report, AI Usage Report.
Interview: I must explain and change the code live without AI, so every part stays simple and readable.

## 2. Decisions (what we chose and why)
| Area | Choice | Why |
|---|---|---|
| Backend | Python + FastAPI | Required by the task (Python backend); small, easy to explain |
| LLM | Gemini free tier, Groq as an alternative behind one interface | Free; two providers let us compare models (bonus) |
| Embeddings | Local `fastembed` (bge-small-en-v1.5) | No API limits when embedding about 50k paragraphs; only query embedding runs in production |
| Vector DB | Qdrant (Cloud free tier) | Supports dense and sparse vectors, so hybrid search lives in one database |
| Dataset | HotpotQA (distractor), about 5k questions, about 50k paragraphs | Meets the 50k requirement and has gold answers and supporting facts for evaluation |
| UI | React (Vite + TypeScript), served by FastAPI | One deployable service; user's preference |
| Hosting | Render (free) + Qdrant Cloud (free) | Free, public URL, data persists in Qdrant |

## 3. Requirements checklist (what must exist)
- [x] 3+ file formats (we plan 5: PDF, TXT/MD, HTML, JSON/JSONL, CSV)
- [x] Text and metadata extraction, chunking, duplicate handling
- [x] Add / update / delete documents (pipeline logic; persisted once the Qdrant store exists)
- [x] 2+ chunking strategies, compared (fixed vs sentence at 800 and 300 chars: no meaningful difference on HotpotQA; kept sentence-800)
- [x] Embeddings + semantic search + hybrid search (semantic + keyword)
- [x] At least one **own** ranking/search component (BM25 encoder, RRF fusion, reranker)
- [x] RAG with an LLM, multi-step reasoning, citations (agent solved 3/3 bridge questions, both paragraphs cited)
- [x] Contradiction detection and abstention when evidence is insufficient (test: conflict detection 1.0 on 5 planted contradictions, abstention recall 1.0, false abstentions 0.05)
- [x] LLM error handling, and at least one tool-calling mechanism (retry/backoff, timeouts, 2 tools)
- [x] Evaluation: 40+ questions (60), Recall@K, MRR, answer correctness, citation accuracy, 2+ configurations, error analysis (docs/EVALUATION.md; test after fixes: agent judge 0.85 vs one-search baseline 0.75)
- [x] Python backend + working UI (upload, manage, ask, view sources) (API in milestone 6; React UI in milestone 8, served by FastAPI at `/`)
- [x] 50,000+ records processed (66,555 HotpotQA paragraphs → 78,730 chunks in Qdrant Cloud)
- [ ] Public deployment, persistence across restarts, secrets protected, deployment description
- [ ] Tests, modular code, documentation

## 4. Milestones (when)
Work in this order. Each milestone ends with passing tests and a git commit, so the history shows real progress.

| # | Milestone | Output | Why now |
|---|---|---|---|
| 1 | Scaffold | Folder layout, config, requirements, pytest setup | Everything else builds on it |
| 2 | Ingestion | Loaders (5 formats), 2 chunkers, dedup, add/update/delete + tests | Data must be in the right shape before search |
| 3 | Retrieval | Qdrant store, own BM25 encoder, RRF fusion, reranker + tests | Core of the engine, and the "own algorithm" requirement |
| 4 | Dataset + indexing | Seeded HotpotQA subset, offline indexing script (about 50k paragraphs) | Needed for real evaluation and the 50k requirement |
| 5 | Agentic RAG | LLM providers, tool calling, query decomposition, cited answers, conflicts, abstention | The "investigation" behavior |
| 6 | API | FastAPI endpoints, SSE streaming | Connects the engine to a UI |
| 7 | Evaluation | 60 questions (simple, multi-hop, unanswerable, contradictory), metrics, config comparison, report | Proves quality and drives improvements |
| 8 | Frontend | React document manager, ask panel, citation/source viewer | Required usable interface |
| 9 | Deployment | Dockerfile, Render, Qdrant Cloud, persistence check | Required public URL |
| 10 | Docs + bonus | README, Evaluation Report, AI Usage Report, prompt-injection tests, caching | Final deliverables |

## 5. How each milestone is done
1. **Plan the module**, then write it with tests.
2. **Run the tests** and a manual check.
3. **Explain it** so I understand it for the interview.
4. **Commit** with a clear message.
5. **Log in `docs/AI_USAGE.md`** what AI wrote and what I changed.

## 6. Risks and how we handle them
| Risk | Mitigation |
|---|---|
| Free LLM rate limits | Retry with backoff, caching, small eval batches, Groq fallback |
| Render free tier sleeps / low RAM (512 MB) | Small embedding model, document the cold start |
| 50k paragraphs slow to embed | Embed offline once, push to Qdrant Cloud |
| Hallucinated answers | Strict grounding prompt, citation check, abstain flag, measured in eval |
| Not being able to explain the code | Keep modules small, review each one after it is written |

## 7. What I need to provide
- Gemini API key (Google AI Studio, free), optional Groq key
- Qdrant Cloud free cluster URL and API key
- Render account connected to the GitHub repo

## 8. Definition of done
All checkboxes in section 3 are ticked, the live URL works, `pytest` passes, the eval report is written, and I can
explain every module without AI.

> Detailed design: see `/Users/zukametreveli/.claude/plans/i-have-project-give-peppy-waffle.md`.
