"use client";

import { Activity, AlertTriangle, Users } from "lucide-react";
import type { Stats } from "@/lib/api";

export function StatsCards({ stats }: { stats: Stats }) {
  return (
    <div className="grid grid-cols-1 sm:grid-cols-3 gap-4">
      <div className="rounded-xl bg-slate-800/80 border border-slate-700 p-4 flex items-center gap-3">
        <Activity className="h-8 w-8 text-cyan-400" />
        <div>
          <p className="text-slate-400 text-sm">Avg wait time</p>
          <p className="text-xl font-semibold">{stats.average_wait_minutes} min</p>
        </div>
      </div>
      <div className="rounded-xl bg-slate-800/80 border border-slate-700 p-4 flex items-center gap-3">
        <AlertTriangle className="h-8 w-8 text-amber-400" />
        <div>
          <p className="text-slate-400 text-sm">Critical handled</p>
          <p className="text-xl font-semibold">{stats.critical_cases_handled}</p>
        </div>
      </div>
      <div className="rounded-xl bg-slate-800/80 border border-slate-700 p-4 flex items-center gap-3">
        <Users className="h-8 w-8 text-emerald-400" />
        <div>
          <p className="text-slate-400 text-sm">In queue</p>
          <p className="text-xl font-semibold">{stats.queue_count}</p>
        </div>
      </div>
    </div>
  );
}
