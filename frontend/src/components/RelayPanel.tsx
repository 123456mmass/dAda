"use client";

import React from "react";
import { RelayData } from "@/context/AppContext";

interface Props {
  relay: RelayData;
}

export default function RelayPanel({ relay }: Props) {
  const isTrip = relay.status === "TRIP";
  const phases = ["A", "B", "C"];

  return (
    <div className={`card overflow-hidden border-t-4 p-5 ${isTrip ? "border-red-500 bg-red-950/20" : "border-indigo-500 bg-indigo-950/10"}`}>
      <div className="mb-6 flex items-center justify-between">
        <div>
          <h2 className="text-xl font-bold tracking-tight text-white uppercase">Relay Status</h2>
          <div className="mt-1 flex items-center gap-2">
            <span className={`h-2 w-2 rounded-full ${isTrip ? "animate-pulse bg-red-400" : "bg-emerald-400"}`} />
            <span className={`text-[10px] font-black uppercase tracking-widest ${isTrip ? "text-red-400" : "text-emerald-400"}`}>
              {relay.status}
            </span>
          </div>
        </div>
        <div className="text-right">
          <div className="text-[10px] font-bold uppercase tracking-widest text-slate-500">Group</div>
          <div className="text-sm font-black text-slate-200">{relay.vector_family} / {relay.vector_group}</div>
        </div>
      </div>

      {/* Main diff status grid */}
      <div className="grid grid-cols-3 gap-3">
        {phases.map((ph, i) => {
          const tripped = relay.trip_phases[i];
          const val = relay.i_diff_amp[i];
          const limit = relay.threshold_amp[i];
          const pct = limit > 0 ? (val / limit) * 100 : 0;

          return (
            <div key={ph} className={`relative overflow-hidden rounded-xl border p-3 transition-all ${tripped ? "border-red-500/50 bg-red-500/10" : "border-slate-800 bg-slate-800/40"}`}>
              <div className="mb-2 flex items-center justify-between">
                <span className={`text-xs font-black ph-${ph.toLowerCase()}`}>PHASE {ph}</span>
                {tripped && <span className="text-[8px] font-bold text-red-400 animate-pulse">TRIP</span>}
              </div>

              <div className="mb-1 text-lg font-black tracking-tighter text-white">
                {val.toFixed(3)}<span className="ml-1 text-[10px] font-normal text-slate-500">A</span>
              </div>

              <div className="mt-2 h-1 w-full overflow-hidden rounded-full bg-slate-900">
                <div
                  className={`h-full transition-all duration-500 ${tripped ? "bg-red-500" : pct > 80 ? "bg-amber-500" : "bg-emerald-500"}`}
                  style={{ width: `${Math.min(pct, 100)}%` }}
                />
              </div>
              <div className="mt-1 flex justify-between text-[8px] font-bold uppercase tracking-tight text-slate-500">
                <span>{limit.toFixed(2)}A Limit</span>
                <span>{Math.round(pct)}%</span>
              </div>
            </div>
          );
        })}
      </div>

      {/* Footer Info */}
      <div className="mt-6 flex gap-4 border-t border-slate-800/50 pt-4">
        <div className="flex-1">
          <div className="text-[9px] font-bold uppercase tracking-widest text-slate-500">Voltage Vector</div>
          <div className="text-sm font-bold text-slate-300">{relay.compensation_group}</div>
        </div>
        <div className="flex-1 text-center">
          <div className="text-[9px] font-bold uppercase tracking-widest text-slate-500">Tap Pos</div>
          <div className="text-sm font-bold text-white">{relay.tap_position}</div>
        </div>
        <div className="flex-1 text-right">
          <div className="text-[9px] font-bold uppercase tracking-widest text-slate-500">System Phase</div>
          <div className="text-sm font-bold text-indigo-400">{relay.system_phase}</div>
        </div>
      </div>
    </div>
  );
}
