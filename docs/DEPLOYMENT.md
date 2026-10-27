# Deploying CaseFile

**Live demo:** https://casefile.metroz.me (Render free tier; the first request after 15 idle minutes takes about a
minute while the server wakes up; the UI shows "waking").

## 1. Architecture
```
Browser ──HTTPS──► Cloudflare DNS ──► Render web service (Docker, free, 512 MB)
  casefile.metroz.me   CNAME, DNS only     │  FastAPI: API + the built React UI at "/"
                                           │  fastembed bge-small (in the image, for query embeddings)
                                           ├──► Qdrant Cloud (free, AWS eu-central-1): chunks + documents
                                           ├──► Gemini API (main LLM)
                                           └──► Groq API (failsafe LLM, when Gemini fails)
```
- **One service.** FastAPI serves both the API and the React UI, so there's one URL, no CORS and one deploy.
- **The server stores nothing on its own disk.** Every document, chunk, vector and duplicate fingerprint lives in
  Qdrant Cloud. A restart, redeploy or sleep on Render loses nothing (section 4).

## 2. The image (`Dockerfile`)
Two stages:
1. `node:24-slim` runs `npm ci && npm run build` → `frontend/dist`. Node isn't in the final image.
2. `python:3.11-slim`:
   - installs only `backend/requirements.txt` (test tools are in `requirements-dev.txt`);
   - **downloads the embedding model during the build** (`FASTEMBED_CACHE_PATH=/app/models`), so a cold start doesn't
     download ~130 MB;
   - copies the API code and the built UI;
   - runs as a non-root user;
   - starts `uvicorn casefile.api.app:app --host 0.0.0.0 --port $PORT` with **one worker**, because each worker would
     load its own embedding model.

`.dockerignore` keeps `.env`, `.git`, `data/`, `eval/`, tests and `node_modules` out of the image.

## 3. Secrets
| Variable | Where it's set |
|---|---|
| `GEMINI_API_KEY`, `GROQ_API_KEY`, `QDRANT_URL`, `QDRANT_API_KEY` | Render dashboard → Environment (encrypted) |
| `LLM_PROVIDER` | `render.yaml` (not a secret) |

- No secret is in the repository or the image. `.env` is git-ignored and in `.dockerignore`; `render.yaml` only
  names the variables (`sync: false`), so Render asks for the values.
- The git history was scanned before the repository was made public: none of the real key values appears in any
  of the 71 commits.
- Errors shown to users contain the provider's message, never a key.
- Secrets are never typed into chat or logs; `.env.example` lists the names with empty values.

## 4. Protecting the public demo
Anyone with the URL can use the site, so two limits apply (both in `config.py`, both on by default):
- **The demo corpus is read-only** (`PROTECT_CORPUS`).
  - Documents indexed from `corpus.jsonl` (HotpotQA) and `contradictory_documents.jsonl` can't be replaced or
    deleted through the API: 403, with a message saying to upload your own file instead. Your own uploads can be
    updated and deleted as usual.
  - The check looks at the **stored** document, not at the upload. A document's id is a hash of its source name, so
    without that, uploading a file *named* `corpus.jsonl` with `{"id": "Flavian dynasty", ...}` would silently replace
    real evidence (status `protected` instead).
  - The indexing and evaluation scripts build their own pipeline without the rule, so re-indexing still works.
- **10 questions per visitor per hour** (`QUESTIONS_PER_HOUR_PER_VISITOR`, 0 = off).
  - Gemini's free tier allows about 500 requests a day and a question costs about 3, so one visitor could otherwise
    use up the whole day's quota for everyone.
  - Over the limit, `/ask` and `/ask/stream` answer 429 with a `Retry-After` header and a plain message.
  - The visitor is the **last** `X-Forwarded-For` entry, which Render's proxy adds. Earlier entries come from the
    visitor and could be faked to dodge the limit.
  - The counts live in memory, so a restart resets them. That's fine for a single-instance demo.

## 5. Persistence
- **Data:** Qdrant Cloud, a managed database outside Render. Uploads, updates and deletes are written there at once.
- **Check:** *(to fill in: upload → restart the service → document still listed)*
- **Limits of the free tiers:**
  - Render sleeps after 15 minutes without requests; waking takes about a minute.
  - Qdrant Cloud suspends a free cluster after a period of inactivity; it has to be resumed in the Qdrant console.

## 6. Domain
- Cloudflare DNS: `CNAME casefile → casefile-h2kd.onrender.com`, **DNS only** (grey cloud).
- Render issues and renews the HTTPS certificate (Let's Encrypt).
- The proxy must stay off: with it on, Cloudflare answers instead of Render, so Render can't verify the domain or
  issue the certificate. That was the first verification failure: the bare domain `metroz.me` was proxied.

## 7. Memory (512 MB)
Render's free tier kills a service that goes over 512 MB, which would take the site down for everyone. So the real
server was measured (resident memory sampled every 0.2 s) while doing real work against Qdrant Cloud and Gemini.

**Questions:**
| Step | Peak |
|---|---|
| Startup + `/health` | 147 MB |
| First question (loads the embedding model) | 367 MB |
| Second question | 379 MB |
| Two questions at the same time | 439 MB |

**Uploads, the real risk.** A 1 MB text file of unique text (reversed corpus paragraphs, so deduplication couldn't
skip it; 1,696 chunks) took the server to **1,142 MB**, more than twice the limit. One upload would have crashed the
public site.

- **Cause:** `EMBEDDING_BATCH_SIZE = 64`. The model's attention tables grow with batch × length², and ONNX Runtime
  keeps the memory it reserved. Measured on the same 1,700 chunks, each batch size in a fresh process:

  | Batch size | Time | Extra memory | Peak |
  |---|---|---|---|
  | 64 (before) | 57 s | +871 MB | 1,184 MB |
  | 32 | 61 s | +373 MB | 688 MB |
  | 16 | 62 s | +274 MB | 589 MB |
  | 8 | 66 s | +122 MB | 441 MB |
  | **4 (now)** | 66 s | **+70 MB** | 404 MB |
- **Fix:** batch size 4 (`retrieval/embeddings.py`), 16% slower than 64.
- **After the fix:** a question followed by the same 1 MB upload peaks at **474 MB** (was 1,142 MB).
- **Ruled out:**
  - Fewer ONNX threads: with 1, 2 or all 10 threads the extra memory stayed at 97–105 MB; 1 thread was only twice
    as slow.
  - Turning off ONNX Runtime's memory pool (`enable_cpu_mem_arena = False`): **worse**, 912 MB instead of 418 MB
    after 60 queries, and 50% slower.
  - A smaller model file: the model is already the quantized `bge-small-en-v1.5-onnx-q` (65 MB).
- **Second fix, a lock around the model** (`FastEmbedEmbedder.lock`):
  - The API runs requests in parallel threads that share one model. Two embeddings at once each need working
    memory, and two first requests on a cold server would **load the model twice** (a test without the lock created
    it 6 times).
  - The lock is taken per batch of 4 chunks, so a question waits behind at most one small batch, never a whole
    upload; a question asked during a 1 MB upload still answered in 23 s. Only embedding is serialized; the LLM part
    of questions still runs in parallel.
  - On the Mac: two questions at once 439 → 416 MB; question **during** a 1 MB upload 423 MB.

**Final check: the real image under Render's limit** (`docker run -m 512m --memory-swap 512m`, Linux, numbers from
the kernel's own cgroup counters `memory.peak` and `oom_kill`):

| Step | Peak | Out-of-memory kills |
|---|---|---|
| Startup | 108 MB | 0 |
| Two first questions at once | 290 MB | 0 |
| A question during a 1 MB upload (worst case) | **404 MB** | 0 |

About 108 MB of headroom. Render's *Metrics* tab is checked after deploying.

**Found by this test:** every question failed in the container with `PermissionError` on `rag/retry.py`. The file was
`-rw-------` on the build machine, Docker's `COPY` keeps permissions, and the server runs as a non-root user. Render
wouldn't have hit it (git stores only the executable bit, so a fresh clone gets normal permissions), but the
Dockerfile now runs `chmod -R a+rX` on the code so the image never depends on the build machine.

## 7b. Upload speed (CPU)
Uploads on Render were very slow: 2 KB took 70 s, and 61 KB (100 chunks) took 332 s, about **3.3 s per chunk**
(on a laptop, ~0.04 s).

- **Cause 1: Render's free tier has a fraction of one CPU**, and embedding is pure computation. In Docker:

  | CPU limit | Threads | Model load | Question embedding | Per chunk |
  |---|---|---|---|---|
  | 1 CPU | 10 (default) | 1.3 s | 0.20 s | 0.87 s |
  | 1 CPU | **1** | 1.1 s | 0.05 s | **0.10 s** |
  | 0.1 CPU | 10 (default) | 18.8 s | 3.7 s | 14.4 s |
  | 0.1 CPU | **1** | 15.6 s | 0.8 s | **3.7 s** |
- **Cause 2: too many threads.** ONNX Runtime starts one thread per core it can *see* (10 here), not per core the
  container may *use*, so the threads fight over the CPU limit. One thread is 4–9× faster under a limit. Fix:
  `EMBEDDING_THREADS = 1` by default (0 = all cores, for bulk indexing on a laptop). Question embedding gets faster
  too.
- **Cause 3: the first request after a wake-up loaded the model** (≈15 s at 0.1 CPU). The server now loads it in a
  background thread at startup, so `/health` answers at once and the first visitor usually doesn't wait.
- **Smaller: two Qdrant lookups per chunk** for duplicate detection: 143 ms per chunk from a laptop in Georgia; about
  5 ms when the server is in the same region as Qdrant (Frankfurt). Could be batched (one lookup per document)
  if it ever matters.

## 8. Deploying a change
1. Push to `main`. Render rebuilds the image and switches over only after `/health` answers (zero-downtime deploy).
2. If a deploy fails, the previous version keeps running. Render → *Events* shows the build log.

## 9. Running the image locally
```
docker build -t casefile .
docker run --rm -p 8000:8000 --env-file .env -m 512m casefile
# open http://localhost:8000
```
