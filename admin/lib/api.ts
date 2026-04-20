const API_BASE = process.env.NEXT_PUBLIC_API_URL || "http://127.0.0.1:8000";

export type QueueEntry = {
  patient_id: number;
  priority: number;
  position: number;
  severity: number;
  arrival_time: string;
  expected_wait_minutes: number;
  /** Display value (minimum 10 min) for consistency with user-facing estimate */
  expected_wait_display_minutes?: number;
  estimated_treatment_minutes?: number;
  mobile?: string | null;
  name?: string | null;
};

export type ReasoningResponse = {
  patient_id: number;
  reasoning: string;
  rag_sources: { content: string }[];
  voice_transcript: string;
  severity?: number;
  symptoms?: string;
};

export type Stats = {
  average_wait_minutes: number;
  critical_cases_handled: number;
  queue_count: number;
};

export async function fetchQueue(): Promise<QueueEntry[]> {
  const r = await fetch(`${API_BASE}/queue`);
  if (!r.ok) throw new Error("Failed to fetch queue");
  return r.json();
}

export async function fetchReasoning(patientId: number): Promise<ReasoningResponse> {
  const r = await fetch(`${API_BASE}/patients/${patientId}/reasoning`);
  if (!r.ok) throw new Error("Failed to fetch reasoning");
  return r.json();
}

export async function fetchStats(): Promise<Stats> {
  const r = await fetch(`${API_BASE}/stats`);
  if (!r.ok) throw new Error("Failed to fetch stats");
  return r.json();
}

export async function completeFirst(): Promise<{ completed: QueueEntry; message: string }> {
  const r = await fetch(`${API_BASE}/queue/complete-first`, { method: "POST" });
  if (!r.ok) {
    const err = await r.json().catch(() => ({}));
    throw new Error(err.detail || "Failed to complete first");
  }
  return r.json();
}

export async function reclassify(patientId: number, severity: number): Promise<{ patient_id: number; severity: number; queue_position: number | null }> {
  const r = await fetch(`${API_BASE}/patients/${patientId}/reclassify`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ severity }),
  });
  if (!r.ok) {
    const err = await r.json().catch(() => ({}));
    throw new Error(err.detail || "Reclassify failed");
  }
  return r.json();
}

export function wsQueueUrl(): string {
  const base = process.env.NEXT_PUBLIC_API_URL || "http://127.0.0.1:8000";
  return base.replace(/^http/, "ws") + "/ws/queue";
}
