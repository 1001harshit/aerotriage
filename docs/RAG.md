# RAG (Retrieval-Augmented Generation) in AeroTriage

## What is RAG here?

The **Clinical Triage Agent** uses RAG to ground the LLM in the **Emergency Severity Index (ESI)** so that triage decisions follow official guidelines instead of the model’s generic knowledge.

- **Document**: ESI handbook (PDF) — `data/esi_handbook.pdf`.
- **Flow**: Patient symptoms → **vector search** over ESI chunks → **top 3 chunks** passed into the LLM prompt as “Context from ESI” → LLM returns severity + **reasoning** + confidence.
- **Reasoning**: The LLM’s short explanation (e.g. “Chest pain with risk factors per ESI suggests level 2”) is stored per patient and shown in the admin “Reasoning” view.
- **RAG sources**: The exact ESI chunk texts used for that triage are stored as **rag_sources** and shown in the admin for transparency and audit.

## Where is the “reason” and RAG data stored?

| What | Where |
|------|--------|
| **Reasoning** (LLM explanation) | SQLite `patients.reasoning` |
| **RAG sources** (ESI chunks used) | SQLite `patients.rag_sources` (JSON array of `{ "content": "..." }`) |
| **Voice transcript** (if voice triage) | SQLite `patients.voice_transcript` |

So: **reason** = `patients.reasoning`; **RAG doc chunks** = `patients.rag_sources`. Both are filled after each triage and returned by **GET /patients/{id}/reasoning** and optionally in **GET /queue** as `reasoning` per patient.

## Pipeline (code)

1. **Indexing (one-time)**  
   - Script: `ai_core/rag/embed_esi.py` (or `embed_pdf.py`).  
   - Loads `data/esi_handbook.pdf`, splits into chunks (e.g. 500 chars, 50 overlap), embeds with **nomic-embed-text** (Ollama), stores in **ChromaDB** under `vector_db/`.

2. **Retrieval at triage**  
   - `ai_core/rag/retriever.py`:  
     - `retrieve(query)` → single string of top 3 chunk texts (used in the LLM prompt).  
     - `retrieve_sources(query)` → list of `{ "content": chunk_text }` (stored as RAG sources for the admin).

3. **Triage agent**  
   - `orchestration/agents/triage_agent.py`:  
     - Calls `retrieve(symptoms)` and `retrieve_sources(symptoms)`, builds prompt with context, gets LLM JSON `{ severity, reasoning, confidence }`, adds `rag_sources` to the result.

4. **Storing reason + RAG**  
   - After `triage_graph.invoke`, `backend/main.py` calls `db.update_patient_reasoning(patient_id, reasoning=..., rag_sources=json.dumps(...), voice_transcript=...)` so every patient has **reason** and **RAG doc** chunks stored.

## How to get “reason” and RAG in the app

- **Per patient (full transparency)**: **GET /patients/{patient_id}/reasoning**  
  Returns `reasoning`, `rag_sources`, `voice_transcript`, plus `severity` and `symptoms`.
- **In the queue list**: **GET /queue**  
  Each entry includes a short `reasoning` line so the dashboard can show it without an extra call. For full RAG sources and transcript, use the reasoning endpoint above.

## If reasoning or RAG sources are empty

- **New columns**: If the DB was created before these fields existed, run the app once so `init_db()` runs and adds `reasoning`, `rag_sources`, `voice_transcript` to `patients`. Existing rows will have NULL until they are triaged again or you backfill.
- **Rule path**: When triage is decided by rules (e.g. “chest pain” → P2), we don’t call the LLM; we set `reasoning = "Rule matched: severity N."` and `rag_sources = []`. So you still get a reason, but no RAG chunks.
- **LLM didn’t return reasoning**: The parser defaults to empty string; improving the prompt or model can reduce that.
