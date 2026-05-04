# rq-rag-api

A small **RAG (Retrieval-Augmented Generation)** API: user questions are answered using chunks from your PDFs stored in **Qdrant**. Heavy work runs in the background via **Redis Queue (RQ)** so the HTTP server stays responsive.

---

## What (in one sentence)

**FastAPI** receives a question, **enqueues** a job on **Redis**, an **RQ worker** retrieves similar text from **Qdrant**, builds a prompt with that context, and calls **OpenRouter** (LLM + embeddings) to produce the answer. You poll **job status** to get the result.

---

## Why this shape

| Piece | Role |
|--------|------|
| **Qdrant** | Vector store: “find document chunks similar to this question.” |
| **Embeddings** | Turn text into vectors so similarity search works. |
| **OpenRouter** | One API for chat model and embedding model (configured like OpenAI). |
| **Redis + RQ** | The RAG pipeline (search + LLM) can take seconds. Doing it inside the HTTP request would tie up the server and risk timeouts. **Queue + worker** runs that work separately. |
| **FastAPI** | Thin layer: accept query, return `job_id`; another endpoint returns the finished answer. |

---

## How the code flows (step by step)

1. **`main.py`**  
   Loads `.env`, starts **Uvicorn** on `0.0.0.0:8000` with the FastAPI `app` from `server.py`.

2. **`server.py` (FastAPI)**  
   - **`GET /`** — Health check.  
   - **`POST /chat?query=...`** — Puts a job on the RQ queue: `process_query` with your `query`. Returns `{"status": "queued", "job_id": "<uuid>"}`.  
   - **`GET /job-status?job_id=...`** — Loads that job from Redis and returns `job.return_value()` (the worker’s return value when the job finished).

3. **`client/rq_client.py`**  
   Creates a shared **`Queue`** connected to **Redis** (`localhost:6379`). The server uses this queue to `enqueue(process_query, query=query)`.

4. **`queues/worker.py`**  
   Defines **`process_query(query: str)`**, which the **RQ worker process** runs when it picks up a job:
   - **`OpenAIEmbeddings`** (via OpenRouter) embeds the question.  
   - **`QdrantVectorStore`** runs **similarity search** on collection `learning_rag`.  
   - Builds a **system prompt** with page content, page labels, and file paths from metadata.  
   - **`OpenAI` client** (OpenRouter base URL) calls **`openai/gpt-4o-mini`** with system + user messages.  
   - Returns the assistant’s text string (that becomes the job’s return value).

```text
User → POST /chat → server enqueues(process_query, query)
                           ↓
                    Redis (job waiting)
                           ↓
              rq worker pulls job → worker.process_query()
                           ↓
         Qdrant similarity_search → OpenRouter chat → return string
                           ↓
User → GET /job-status?job_id=... → same string in JSON as "result"
```

---

## Prerequisites

- **Python** with dependencies from `requirements.txt`.
- **Redis (or Valkey)** on port **6379** — e.g. `docker compose up` in this repo (see `docker-compose.yml`).
- **Qdrant** at `http://localhost:6333` with collection **`learning_rag`** already populated (this repo does not include the ingestion script; the worker expects that collection to exist).
- **`.env`** with at least `OPENROUTER_API_KEY` (used by `queues/worker.py`).

---

## How to run

1. Start Redis/Valkey:  
   `docker compose up -d`  
   (or any Redis on `localhost:6379`.)

2. Ensure Qdrant is running and the `learning_rag` collection exists.

3. Start the API:  
   `python main.py`  
   (serves on port **8000**.)

4. In a **separate** terminal, start an RQ worker from the project root (Windows-friendly worker class):  
   `rq worker --worker-class rq.worker.SimpleWorker`

5. Call **`POST /chat?query=Your question here`**, note **`job_id`**, then **`GET /job-status?job_id=...`** until the job has finished and you get the answer in **`result`**.

---

## File map

| File | Purpose |
|------|---------|
| `main.py` | Entry point: Uvicorn + `server.app`. |
| `server.py` | Routes: `/`, `/chat`, `/job-status`. |
| `client/rq_client.py` | Redis connection + shared `Queue`. |
| `queues/worker.py` | RAG + LLM logic executed by the worker. |
| `docker-compose.yml` | Valkey/Redis on 6379. |
| `requirements.txt` | Python packages. |

---

## Notes when reading the code

- **`/job-status`** assumes the job exists and is finished; if the job is still running or the id is wrong, you may need extra checks in `server.py` (not implemented here).
- The worker prints progress to the worker terminal (`print` in `process_query`).

For deeper debugging of RQ jobs (job id, failures, retries), see the [RQ documentation](https://python-rq.org/docs/).
