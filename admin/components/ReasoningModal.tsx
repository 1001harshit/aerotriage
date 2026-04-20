"use client";

import { X } from "lucide-react";
import type { ReasoningResponse } from "@/lib/api";

export function ReasoningModal({
  data,
  onClose,
}: {
  data: ReasoningResponse | null;
  onClose: () => void;
}) {
  if (!data) return null;
  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-black/70" onClick={onClose}>
      <div
        className="bg-slate-800 border border-slate-600 rounded-xl max-w-2xl w-full max-h-[80vh] overflow-auto shadow-xl"
        onClick={(e) => e.stopPropagation()}
      >
        <div className="sticky top-0 bg-slate-800 border-b border-slate-600 p-4 flex justify-between items-center">
          <h3 className="text-lg font-semibold">AI reasoning — Patient #{data.patient_id}</h3>
          <button onClick={onClose} className="p-1 rounded hover:bg-slate-700">
            <X className="h-5 w-5" />
          </button>
        </div>
        <div className="p-4 space-y-4">
          {(!data.reasoning && (!data.rag_sources || data.rag_sources.length === 0)) && (
            <p className="text-amber-500/90 text-sm">
              No reasoning or RAG data stored. This can happen if the patient was added before the confirm flow or if triage did not return data.
            </p>
          )}
          <div>
            <p className="text-slate-400 text-sm mb-1">Reasoning</p>
            <p className="text-slate-200">{data.reasoning || "—"}</p>
          </div>
          {data.voice_transcript ? (
            <div>
              <p className="text-slate-400 text-sm mb-1">Voice transcript</p>
              <p className="text-slate-200 text-sm italic">&ldquo;{data.voice_transcript}&rdquo;</p>
            </div>
          ) : null}
          <div>
            <p className="text-slate-400 text-sm mb-1">RAG sources (ESI context used)</p>
            <ul className="space-y-2">
              {(data.rag_sources || []).map((s, i) => (
                <li key={i} className="text-sm text-slate-300 bg-slate-900/50 rounded p-2 border border-slate-700">
                  {s.content}
                </li>
              ))}
              {(!data.rag_sources || data.rag_sources.length === 0) && <li className="text-slate-500">—</li>}
            </ul>
          </div>
        </div>
      </div>
    </div>
  );
}
