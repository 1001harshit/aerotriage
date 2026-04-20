# Where data is stored and how to connect

## Overview

| Store | Purpose | Location / connection |
|-------|--------|------------------------|
| **SQLite** | Patients, queue, reasoning, RAG, transcript | File: `data/aerotriage.db` |
| **Redis** | Real-time queue (ZSET) | `redis://localhost:6379` or `REDIS_URL` |
| **ChromaDB** | ESI RAG vectors | Directory: `vector_db/` |

---

## 1. SQLite (main record store)

**Path**: `data/aerotriage.db` (relative to project root). Created automatically on first run.

**Tables**:

- **patients**  
  `id`, `symptoms`, `severity`, `confidence`, `arrival_time`, `status`, `flag_for_review`, `mobile`, `completed_at`, **`reasoning`**, **`rag_sources`** (JSON text), **`voice_transcript`**
- **queue**  
  `patient_id`, `priority`, `created_at` (who is currently in the queue)

**How to “connect”**:

- No server. Ensure the process has read/write access to the project directory.
- To change path: set `DB_PATH` in `backend/database.py` (e.g. to an absolute path or another folder).
- To inspect:  
  `sqlite3 data/aerotriage.db`  
  then e.g. `.tables`, `SELECT id, severity, reasoning FROM patients LIMIT 5;`

---

## 2. Redis (queue ZSET)

**Role**: Holds the live triage queue as a sorted set: `triage_queue`, score = priority, value = `patient_id`. Written on add/complete; **queue order for the API is computed from SQLite + aging**, but Redis is kept in sync for consistency.

**Default URL**: `redis://localhost:6379` (see `backend/redis_queue.py`).

**How to connect**:

1. Install and start Redis (e.g. `brew install redis && brew services start redis`, or Docker: `docker run -d -p 6379:6379 redis`).
2. Check: `redis-cli ping` → `PONG`.
3. Optional: set env **`REDIS_URL`** before starting the app, e.g.  
   `export REDIS_URL=redis://YOUR_HOST:6379`  
   (or a Redis Cloud URL). No code change needed; the client uses `REDIS_URL`.

---

## 3. ChromaDB (RAG vectors)

**Role**: Stores embeddings of the ESI handbook chunks. Used by `ai_core/rag/retriever.py` for `retrieve()` and `retrieve_sources()`.

**Location**: Directory `vector_db/` (created when you run `embed_esi.py` or `embed_pdf.py`).

**How to “connect”**:

- No separate server by default; ChromaDB runs embedded. Path is set in code (`persist_directory="./vector_db"`). Ensure the app runs from the project root so this path is correct.
- To repopulate: put `data/esi_handbook.pdf` in place and run  
  `python -m ai_core.rag.embed_esi`

---

## Summary

- **Reason and RAG doc**: Stored in **SQLite** (`patients.reasoning`, `patients.rag_sources`, `patients.voice_transcript`). Filled after each triage; read via GET /patients/{id}/reasoning and GET /queue.
- **SQLite**: Use `data/aerotriage.db`; change path in `backend/database.py` if needed.
- **Redis**: Start Redis, set `REDIS_URL` if not using localhost.
- **ChromaDB**: Use `vector_db/`; populate once with the ESI PDF and the embed script.
