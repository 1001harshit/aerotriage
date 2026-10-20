# AeroTriage 2026

Offline-first AI-powered medical triage using ESI (Emergency Severity Index), LangGraph, RAG (ChromaDB), and Ollama.

## Requirements

- Python 3.9+
- Ollama with `llama3.2:3b` and `nomic-embed-text`
- Redis (for real-time queue)
- Optional: `data/esi_handbook.pdf` for RAG; Whisper (faster-whisper) for voice triage

## Setup

1. Create venv and install: `pip install -r requirements.txt`
2. Place ESI handbook at `data/esi_handbook.pdf`, then run: `python -m ai_core.rag.embed_esi` (or use `embed_pdf.py`).
3. Start Redis locally (e.g. `redis-server`).
4. Start Ollama and pull `llama3.2:3b` and `nomic-embed-text`.

## Run

From project root:

```bash
uvicorn backend.main:app --reload
```

- **POST /triage** — Body: `{ "symptoms": "...", "mobile"?: "..." }`. Returns `patient_id`, `severity`, `confidence`, `queue_position`, `flag_for_review`, `mobile?`.
- **GET /queue** — Ordered triage queue with `expected_wait_minutes`, `estimated_treatment_minutes`, `mobile`, `reasoning`.
- **POST /queue/complete-first** — Remove first patient (mark as seen); broadcasts to WebSocket.
- **POST /voice-triage** — Upload audio; Whisper → triage pipeline.
- **GET /patients/{id}/reasoning** — AI transparency: reasoning, RAG sources, voice transcript.
- **POST /patients/{id}/reclassify** — Body: `{ "severity": 1-5 }`. Update severity and queue.
- **GET /stats** — Analytics: average_wait_minutes, critical_cases_handled, queue_count.
- **WebSocket /ws/queue** — Live queue updates for admin dashboard.
- **POST /webhooks/whatsapp** — Twilio WhatsApp: send `Body` (symptoms) and `From`; returns TwiML with queue position and expected wait. See `docs/WHATSAPP.md`.

## Security

The backend stores patient names, phone numbers and symptoms, so lock it down before it is reachable from anywhere but your own machine:

| Variable | Effect |
|---|---|
| `ADMIN_API_KEY` | Staff routes (`/queue`, `/queue/complete-first`, `/stats`, `/patients/*`) require it in an `X-Admin-Key` header, and `/ws/queue` requires it as `?key=`. Unset = open (local dev only; a warning is logged at startup). |
| `NEXT_PUBLIC_ADMIN_API_KEY` | Set in `admin/.env.local` to the same value so the dashboard can call those routes. |
| `TWILIO_AUTH_TOKEN` | `/webhooks/whatsapp` rejects requests without a valid `X-Twilio-Signature`. |
| `PUBLIC_WEBHOOK_URL` | The exact URL configured in Twilio (e.g. your ngrok URL + `/webhooks/whatsapp`). Needed behind a proxy or tunnel, because the signature covers the URL Twilio called. |

The admin key ships in the dashboard's browser bundle, so it keeps strangers off the API but is not a replacement for real staff login.

`data/aerotriage.db` is created on first run and is git-ignored. Never commit it.

## Tests

```bash
python -m unittest discover -s tests -t .
```

## Data

- SQLite: `data/aerotriage.db` (patients and queue history).
- Redis: key `triage_queue` (sorted set, score = priority).
- Vector DB: `vector_db/` (ChromaDB for ESI RAG).

See **docs/DATA_STORAGE.md** for where data lives and how to connect. See **docs/RAG.md** for how the “reason” and RAG doc are stored and used.

## Admin dashboard (run independently)

From project root:

```bash
cd admin && npm install && npm run dev
```

Open http://localhost:3000. Ensure the backend is running on http://127.0.0.1:8000 (CORS allows origin 3000). The dashboard uses WebSocket for live queue updates, shows reasoning/RAG/transcript, and provides Call Next, Re-classify, and stats.

## Optional: MCP

The spec mentions Model Context Protocol. To expose triage as MCP tools, add a separate MCP server module that calls the triage pipeline.
