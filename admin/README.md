# AeroTriage Admin Dashboard

Run **independently** from the main backend. Connects to the FastAPI backend for live queue, stats, reasoning, and actions.

## Prerequisites

- Node.js 18+
- Backend running at `http://127.0.0.1:8000` (or set `NEXT_PUBLIC_API_URL`)

## Run

```bash
cd admin
npm install
npm run dev
```

Open [http://localhost:3000](http://localhost:3000).

## Environment

- `NEXT_PUBLIC_API_URL` — Backend base URL (default: `http://127.0.0.1:8000`). WebSocket URL is derived from this.

## Features

- **Live queue** — WebSocket updates when triage or "Call Next" runs; fallback polling if WS fails.
- **Severity colors** — P1 red, P2 amber, P3–5 blue.
- **Reasoning** — Click "Reasoning" to see AI explanation, RAG sources, and voice transcript.
- **Call Next** — Removes first patient from queue (Mark as Seen).
- **Re-classify** — Change severity via dropdown; updates queue.
- **Stats** — Average wait time, critical cases handled, queue count.
- **Filter** — "Show only critical (P1–P2)".
