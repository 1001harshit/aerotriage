"use client";

import { Phone, RefreshCw, Eye } from "lucide-react";
import type { QueueEntry } from "@/lib/api";

function severityBg(severity: number): string {
  if (severity === 1) return "bg-red-900/50 border-red-600";
  if (severity === 2) return "bg-amber-900/50 border-amber-600";
  return "bg-sky-900/30 border-sky-700";
}

export function LiveQueueTable({
  queue,
  onReasoning,
  onCallNext,
  onReclassify,
  onlyCritical,
}: {
  queue: QueueEntry[];
  onReasoning: (id: number) => void;
  onCallNext: () => void;
  onReclassify: (id: number, severity: number) => void;
  onlyCritical: boolean;
}) {
  const filtered = onlyCritical ? queue.filter((e) => e.severity <= 2) : queue;

  return (
    <div className="rounded-xl border border-slate-700 overflow-hidden">
      <div className="overflow-x-auto">
        <table className="w-full text-left">
          <thead className="bg-slate-800/80 border-b border-slate-700">
            <tr>
              <th className="p-3 font-medium text-slate-300">#</th>
              <th className="p-3 font-medium text-slate-300">Name</th>
              <th className="p-3 font-medium text-slate-300">Phone</th>
              <th className="p-3 font-medium text-slate-300">Patient ID</th>
              <th className="p-3 font-medium text-slate-300">Severity</th>
              <th className="p-3 font-medium text-slate-300">Expected wait</th>
              <th className="p-3 font-medium text-slate-300">Arrival</th>
              <th className="p-3 font-medium text-slate-300">Actions</th>
            </tr>
          </thead>
          <tbody>
            {filtered.length === 0 ? (
              <tr>
                <td colSpan={8} className="p-6 text-center text-slate-500">
                  No patients in queue
                </td>
              </tr>
            ) : (
              filtered.map((e) => (
                <tr
                  key={e.patient_id}
                  className={`border-b border-slate-700/50 ${severityBg(e.severity)}`}
                >
                  <td className="p-3 font-mono">{e.position}</td>
                  <td className="p-3">{e.name ?? "—"}</td>
                  <td className="p-3 text-slate-300">{e.mobile ?? "—"}</td>
                  <td className="p-3">{e.patient_id}</td>
                  <td className="p-3">
                    <span className="font-semibold">P{e.severity}</span>
                  </td>
                  <td className="p-3">{(e.expected_wait_display_minutes ?? e.expected_wait_minutes) ?? 0} min</td>
                  <td className="p-3 text-slate-400 text-sm">
                    {e.arrival_time ? new Date(e.arrival_time).toLocaleTimeString() : "—"}
                  </td>
                  <td className="p-3 flex flex-wrap gap-2">
                    <button
                      onClick={() => onReasoning(e.patient_id)}
                      className="inline-flex items-center gap-1 px-2 py-1 rounded bg-slate-700 hover:bg-slate-600 text-sm"
                    >
                      <Eye className="h-3.5 w-3.5" /> Reasoning
                    </button>
                    {e.position === 1 && (
                      <button
                        onClick={onCallNext}
                        className="inline-flex items-center gap-1 px-2 py-1 rounded bg-emerald-700 hover:bg-emerald-600 text-sm"
                      >
                        <Phone className="h-3.5 w-3.5" /> Call Next
                      </button>
                    )}
                    <select
                      className="bg-slate-700 rounded px-2 py-1 text-sm"
                      value={e.severity}
                      onChange={(ev) => onReclassify(e.patient_id, Number(ev.target.value))}
                    >
                      {[1, 2, 3, 4, 5].map((s) => (
                        <option key={s} value={s}>P{s}</option>
                      ))}
                    </select>
                  </td>
                </tr>
              ))
            )}
          </tbody>
        </table>
      </div>
    </div>
  );
}
