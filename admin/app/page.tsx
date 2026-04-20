"use client";

import { useCallback, useEffect, useState } from "react";
import { RefreshCw } from "lucide-react";
import {
  fetchQueue,
  fetchStats,
  fetchReasoning,
  completeFirst,
  reclassify,
  wsQueueUrl,
  type QueueEntry,
  type Stats,
  type ReasoningResponse,
} from "@/lib/api";
import { StatsCards } from "@/components/StatsCards";
import { LiveQueueTable } from "@/components/LiveQueueTable";
import { ReasoningModal } from "@/components/ReasoningModal";

export default function AdminPage() {
  const [queue, setQueue] = useState<QueueEntry[]>([]);
  const [stats, setStats] = useState<Stats | null>(null);
  const [onlyCritical, setOnlyCritical] = useState(false);
  const [reasoning, setReasoning] = useState<ReasoningResponse | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const loadQueue = useCallback(async () => {
    try {
      const q = await fetchQueue();
      setQueue(q);
      setError(null);
    } catch (e) {
      setError(e instanceof Error ? e.message : "Failed to load queue");
    }
  }, []);

  const loadStats = useCallback(async () => {
    try {
      const s = await fetchStats();
      setStats(s);
    } catch {
      setStats({
        average_wait_minutes: 0,
        critical_cases_handled: 0,
        queue_count: 0,
      });
    }
  }, []);

  useEffect(() => {
    loadQueue();
    loadStats();
  }, [loadQueue, loadStats]);

  useEffect(() => {
    const url = wsQueueUrl();
    let ws: WebSocket | null = null;
    try {
      ws = new WebSocket(url);
      ws.onmessage = (event) => {
        try {
          const msg = JSON.parse(event.data);
          if (msg.type === "queue_update" && Array.isArray(msg.queue)) {
            setQueue(msg.queue);
          }
        } catch {}
      };
      ws.onclose = () => {
        setTimeout(() => loadQueue(), 2000);
      };
    } catch {
      // Fallback to polling if WS fails
      const t = setInterval(loadQueue, 5000);
      return () => clearInterval(t);
    }
    return () => {
      ws?.close();
    };
  }, [loadQueue]);

  const handleReasoning = async (patientId: number) => {
    setLoading(true);
    try {
      const r = await fetchReasoning(patientId);
      setReasoning(r);
    } catch (e) {
      setError(e instanceof Error ? e.message : "Failed to load reasoning");
    } finally {
      setLoading(false);
    }
  };

  const handleCallNext = async () => {
    setLoading(true);
    setError(null);
    try {
      await completeFirst();
      await loadQueue();
      await loadStats();
    } catch (e) {
      setError(e instanceof Error ? e.message : "Failed to complete first");
    } finally {
      setLoading(false);
    }
  };

  const handleReclassify = async (patientId: number, severity: number) => {
    setLoading(true);
    setError(null);
    try {
      await reclassify(patientId, severity);
      await loadQueue();
    } catch (e) {
      setError(e instanceof Error ? e.message : "Reclassify failed");
    } finally {
      setLoading(false);
    }
  };

  return (
    <main className="min-h-screen p-6 max-w-6xl mx-auto">
      <div className="flex flex-col gap-6">
        <div className="flex flex-wrap items-center justify-between gap-4">
          <h1 className="text-2xl font-bold text-slate-100">AeroTriage 2026 — Queue Dashboard</h1>
          <div className="flex items-center gap-3">
            <label className="flex items-center gap-2 text-sm text-slate-400">
              <input
                type="checkbox"
                checked={onlyCritical}
                onChange={(e) => setOnlyCritical(e.target.checked)}
                className="rounded border-slate-600 bg-slate-800"
              />
              Show only critical (P1–P2)
            </label>
            <button
              onClick={() => { loadQueue(); loadStats(); }}
              className="inline-flex items-center gap-2 px-3 py-1.5 rounded-lg bg-slate-700 hover:bg-slate-600 text-sm"
            >
              <RefreshCw className="h-4 w-4" /> Refresh
            </button>
          </div>
        </div>

        {error && (
          <div className="rounded-lg bg-red-900/30 border border-red-700 text-red-200 px-4 py-2 text-sm">
            {error}
          </div>
        )}

        {stats && <StatsCards stats={stats} />}

        <LiveQueueTable
          queue={queue}
          onReasoning={handleReasoning}
          onCallNext={handleCallNext}
          onReclassify={handleReclassify}
          onlyCritical={onlyCritical}
        />
      </div>

      {loading && (
        <div className="fixed bottom-4 right-4 px-4 py-2 rounded-lg bg-slate-800 border border-slate-600 text-sm">
          Loading…
        </div>
      )}

      <ReasoningModal data={reasoning} onClose={() => setReasoning(null)} />
    </main>
  );
}
