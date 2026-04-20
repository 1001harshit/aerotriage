# AeroTriage 2026 — What You Have, What’s Left, How to Test, and Setup

---

## 1. What You Have (Implemented)

| Area | Implemented |
|------|-------------|
| **Triage pipeline** | Privacy Guard → Symptom Extractor → Rule Engine → Clinical Triage (RAG + LLM) → Confidence Validator → Scheduler. Conditional: rule hit skips LLM. |
| **Storage** | SQLite: `patients` (symptoms, severity, confidence, arrival_time, status, flag_for_review, mobile, completed_at), `queue` (patient_id, priority, created_at). Redis: ZSET `triage_queue` (written on add/complete; queue order is computed from SQLite + aging). |
| **APIs** | **POST /triage** (body: `symptoms`, optional `mobile`). **GET /queue** (ordered, with expected_wait_minutes, estimated_treatment_minutes, mobile). **POST /queue/complete-first** (remove first, set completed_at). **POST /voice-triage** (audio upload → Whisper → triage). |
| **Queue logic** | Priority aging `(6 - severity) + 0.05 * waiting_minutes`; FIFO tie-break; learned avg treatment time by severity from completed patients; expected wait = sum of estimated times for patients ahead. |
| **Patient contact** | Optional `mobile` stored and returned (for WhatsApp). |
| **RAG** | ChromaDB + nomic-embed-text; retriever returns top 3 chunks; triage agent returns JSON `{ severity, reasoning, confidence }`. |
| **Voice** | faster-whisper (large-v3); POST /voice-triage. |

**Not implemented yet:** Admin Dashboard (live UI), WebSockets, WhatsApp integration, MCP, AI “Reasoning” API for the dashboard.

---

## 2. What’s Remaining (Including Admin Portal)

| Item | Description |
|------|-------------|
| **Admin Queue Dashboard** | Next.js UI: live queue table, color by severity (P1–P5), “Reasoning” column (RAG + transcript), buttons: Call Next / Re-classify / Mark as Seen, analytics cards (avg wait, critical cases, load). |
| **WebSockets** | FastAPI WebSocket endpoint that pushes queue updates when triage completes or “complete-first” is called so the dashboard updates in real time without polling. |
| **AI Transparency API** | Endpoint (or field in queue) that returns for a patient: triage **reasoning** (from LLM JSON), **RAG source** chunks, and **Whisper transcript** (if voice). Requires storing reasoning/transcript per patient (currently not stored). |
| **WhatsApp integration** | Connect incoming WhatsApp messages to POST /triage (e.g. Twilio, WhatsApp Business API, or a bridge); use stored `mobile` to send queue position / expected time back. |
| **Re-classify** | API to re-run triage for a patient and update severity/queue (new endpoint + optional “reason” for audit). |
| **MCP (optional)** | Expose triage as MCP tools for external agents. |

---

## 3. How to Test What You Have

### Prerequisites
- Python 3.9+ with venv, `pip install -r requirements.txt`
- **Ollama** running: `ollama pull llama3.2:3b` and `ollama pull nomic-embed-text`
- **Redis** running: `redis-server` (or Docker: `docker run -d -p 6379:6379 redis`)
- **SQLite**: no server; `data/aerotriage.db` is created on first run
- Optional: `data/esi_handbook.pdf` + run `python -m ai_core.rag.embed_esi` once

### Start backend
From project root:
```bash
source venv/bin/activate   # or venv\Scripts\activate on Windows
uvicorn backend.main:app --reload
```
Base URL: `http://127.0.0.1:8000`.

### Test with browser (Swagger)
1. Open **http://127.0.0.1:8000/docs**.
2. **POST /triage** — Try it out, body: `{ "symptoms": "chest pain and dizziness", "mobile": "+919876543210" }`. Check 200 and `patient_id`, `severity`, `queue_position`, `mobile`.
3. **GET /queue** — Try it out. You should see one entry with `position`, `expected_wait_minutes`, `estimated_treatment_minutes`, `mobile`.
4. **POST /queue/complete-first** — Try it out. First patient is removed; response includes `completed`.
5. **GET /queue** again — Should be empty (or next patient first). Add more via POST /triage and see positions and expected times update.
6. **POST /voice-triage** — Upload a short audio file (e.g. WAV/WebM) with speech; check triage response.

### Test with curl
```bash
# Triage with mobile
curl -X POST http://127.0.0.1:8000/triage \
  -H "Content-Type: application/json" \
  -d '{"symptoms":"cough and cold","mobile":"+919876543210"}'

# Get queue (with expected times and learned estimates)
curl http://127.0.0.1:8000/queue

# Complete first patient
curl -X POST http://127.0.0.1:8000/queue/complete-first
```

### What to verify
- **Priority aging**: Add two severity-2 patients a few minutes apart; GET /queue shows different `priority` and order (oldest first when tie).
- **Learned time**: Complete a few patients (POST /queue/complete-first), then add new ones; GET /queue should show `estimated_treatment_minutes` and `expected_wait_minutes` based on severity (after a few completions per severity).

---

## 4. Connecting to Database and Redis

### SQLite (already used)
- **Where**: `data/aerotriage.db` (relative to project root). Created automatically on first import of `backend.database`.
- **To “connect”**: No server. Ensure the `data/` directory exists and the process has write permission. For a different path, change `DB_PATH` in `backend/database.py`.
- **Inspect**: `sqlite3 data/aerotriage.db` then `.tables`, `SELECT * FROM patients;`, `SELECT * FROM queue;`.

### Redis (required for current code)
- **Default**: App uses `REDIS_URL=redis://localhost:6379` (see `backend/redis_queue.py`). Scheduler writes to Redis on add; complete-first removes from Redis.
- **What you need to do**:
  1. **Install Redis** (pick one):
     - **macOS**: `brew install redis` then `brew services start redis`
     - **Linux**: `sudo apt install redis-server` / `sudo systemctl start redis`
     - **Docker**: `docker run -d --name redis -p 6379:6379 redis`
  2. **Check it’s running**: `redis-cli ping` → `PONG`.
  3. **Optional (different host/port)**: Set env before starting the app:  
     `export REDIS_URL=redis://YOUR_HOST:6379`  
     (e.g. `redis://127.0.0.1:6379` or a cloud Redis URL).
- **If Redis is down**: Scheduler’s `add_to_queue` and complete-first’s `remove_from_queue` will raise when calling Redis. Queue **order** and **expected times** still come from SQLite; only the Redis ZSET is missing (used for consistency with the spec, not for current GET /queue order).

### Summary
| Component | What to do |
|-----------|------------|
| **SQLite** | Ensure `data/` exists; DB path in `backend/database.py` if needed. |
| **Redis** | Install and start Redis; set `REDIS_URL` if not localhost:6379. |

---

## 5. What You’d Need for the Admin Portal (Architect Prompt)

To match the “Admin Portal Architect” prompt (live dashboard, WebSockets, AI transparency):

### A. Backend (FastAPI)
1. **WebSocket manager**  
   - In `main.py` (or a new module): maintain a set of connected WebSocket clients; when POST /triage or POST /queue/complete-first runs, broadcast the new queue payload (e.g. call `get_queue_entries()` and send JSON to all clients).
2. **WebSocket endpoint**  
   - e.g. `GET /ws/queue` that accepts connections and pushes queue updates (and optionally “triage completed” events).
3. **AI Transparency / Reasoning API**  
   - Store per run: `reasoning` (from triage JSON), RAG chunks used, and optional Whisper transcript.  
   - Add fields to DB (e.g. `reasoning`, `rag_sources`, `voice_transcript` on `patients` or a `triage_runs` table) and populate them in the graph/scheduler.  
   - New endpoint, e.g. **GET /patients/{id}/reasoning**, returning `{ reasoning, rag_sources, voice_transcript }` for the dashboard “Reasoning” column/modal.
4. **Re-classify**  
   - e.g. **POST /patients/{id}/reclassify** with optional new severity or “re-run triage”; update queue and DB.

### B. Frontend (Next.js)
1. **Stack**: Next.js, Tailwind v4, Lucide, shadcn/ui, TanStack Table.
2. **Live feed**: Table of patients from GET /queue; sort by urgency (already ordered by backend); color rows by severity (e.g. red P1, yellow P2, blue P3–5).
3. **WebSocket client**: Connect to `ws://.../ws/queue`; on message, replace table data so the list updates without refresh.
4. **Reasoning modal**: For each row, “Reasoning” button opens a modal that calls GET /patients/{id}/reasoning and shows RAG source + transcript + LLM reasoning.
5. **Actions**: Buttons that call:
   - “Call Next” → POST /queue/complete-first
   - “Mark as Seen” → same or a dedicated endpoint
   - “Re-classify” → POST /patients/{id}/reclassify (then refresh or get new queue via WebSocket).
6. **Analytics cards**: “Average Wait Time”, “Critical Cases Handled”, “Doctor Load” — computed from GET /queue and optional GET /stats (you can add a small stats endpoint from SQLite: avg wait, count by severity, etc.).
7. **Filter**: “Show only Critical” (e.g. severity 1–2) / “Show All” — client-side filter on the queue array.

### C. WhatsApp
- Use Twilio API, WhatsApp Business API, or similar to receive messages; map incoming message to **POST /triage** with `symptoms` (and `mobile` from sender).  
- Use stored `mobile` and your provider to send replies (e.g. “You are position N, expected wait ~X minutes”).

---

## 6. Quick Reference: Current API Contract

| Method | Endpoint | Body / Params | Response |
|--------|----------|---------------|----------|
| POST | /triage | `{ "symptoms": string, "mobile"?: string }` | `patient_id`, `severity`, `confidence`, `queue_position`, `flag_for_review`, `mobile?` |
| GET | /queue | — | Array of `{ patient_id, priority, position, severity, arrival_time, expected_wait_minutes, estimated_treatment_minutes, mobile? }` |
| POST | /queue/complete-first | — | `{ completed: <first patient>, message }` or 404 |
| POST | /voice-triage | form: `audio` file | Same shape as POST /triage, or `{ error }` |

---

You can use this file as the single place for “what we have”, “what’s left”, “how to test”, and “what to do for DB/Redis and Admin Portal”.
