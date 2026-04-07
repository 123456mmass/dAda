"use client";

import React, { useState } from "react";
import { useApp } from "@/context/AppContext";
import RelayPanel from "@/components/RelayPanel";
import BiasChart from "@/components/BiasChart";

const defaultRelay = {
  system_phase: "IDLE",
  status: "NORMAL",
  i_diff: [0, 0, 0],
  i_bias: [0, 0, 0],
  trip_phases: [false, false, false],
  thresholds: [0.2, 0.2, 0.2],
  vector_group: "",
  vector_family: "UNKNOWN",
  compensation_group: "UNKNOWN",
  tap_position: 1,
  trip_time: null,
  reset_time: null,
  trip_count: 0,
  last_trip_phases: [] as string[],
  i_hv_pu: [0, 0, 0],
  i_lv_pu: [0, 0, 0],
  i_lv_comp: [0, 0, 0],
  i_hv_amp: [0, 0, 0],
  i_lv_amp: [0, 0, 0],
  i_hv_ref_amp: [0, 0, 0],
  i_lv_ref_amp: [0, 0, 0],
  i_diff_amp: [0, 0, 0],
  i_bias_amp: [0, 0, 0],
  threshold_amp: [0, 0, 0],
  inrush_block_active: false,
  inrush_block_remaining_ms: 0,
  detection: null,
};

export default function RelayPage() {
  const { data, backendUrl } = useApp();
  const relay = data?.relay || defaultRelay;
  const mode = data?.mode || "simulation";
  const [faultActive, setFaultActive] = useState(false);
  const [faultPhases, setFaultPhases] = useState(["A", "B", "C"]);
  const [faultFactor, setFaultFactor] = useState(3.0);

  const injectFault = async () => {
    try {
      await fetch(`${backendUrl}/api/modbus/fault/inject`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          phases: faultPhases,
          factor: faultFactor,
          side: "lv",
        }),
      });
      setFaultActive(true);
    } catch {}
  };

  const clearFault = async () => {
    try {
      await fetch(`${backendUrl}/api/modbus/fault/clear`, { method: "POST" });
      setFaultActive(false);
    } catch {}
  };

  return (
    <div className="p-4">
      <div className="grid grid-cols-1 gap-4 lg:grid-cols-2">
        <RelayPanel relay={relay} />

        <div className="space-y-4">
          <BiasChart relay={relay} />
          <div className="card p-4">
            <h3 className="mb-3 text-sm font-semibold text-slate-300">
              Current Comparison (A)
            </h3>
            {relay.inrush_block_active && (
              <div className="mb-3 rounded-lg border border-amber-500/30 bg-amber-500/10 px-3 py-2 text-xs text-amber-200">
                กำลังบล็อก Trip ชั่วคราวช่วง Inrush เหลือประมาณ{" "}
                {Math.ceil((relay.inrush_block_remaining_ms ?? 0) / 100) / 10}{" "}
                วินาที
              </div>
            )}

            <div className="overflow-x-auto">
              <table className="w-full text-xs">
                <thead>
                  <tr className="border-b border-slate-700 text-slate-500">
                    <th className="px-2 py-2 text-left">เฟส</th>
                    <th className="px-2 py-2 text-right">HV Raw</th>
                    <th className="px-2 py-2 text-right">LV Raw</th>
                    <th className="px-2 py-2 text-right">HV Ref</th>
                    <th className="px-2 py-2 text-right">LV Ref</th>
                    <th className="px-2 py-2 text-right">I_diff</th>
                    <th className="px-2 py-2 text-right">Threshold</th>
                    <th className="px-2 py-2 text-center">สถานะ</th>
                  </tr>
                </thead>
                <tbody>
                  {["A", "B", "C"].map((phase, idx) => (
                    <tr
                      key={phase}
                      className={`border-b border-slate-800 ${
                        relay.trip_phases[idx] ? "bg-red-900/20" : ""
                      }`}
                    >
                      <td
                        className={`px-2 py-2 font-semibold ${
                          idx === 0
                            ? "phase-a"
                            : idx === 1
                            ? "phase-b"
                            : "phase-c"
                        }`}
                      >
                        {phase}
                      </td>
                      <td className="px-2 py-2 text-right font-mono text-amber-300">
                        {(relay.i_hv_amp?.[idx] ?? 0).toFixed(2)}
                      </td>
                      <td className="px-2 py-2 text-right font-mono text-cyan-300">
                        {(relay.i_lv_amp?.[idx] ?? 0).toFixed(2)}
                      </td>
                      <td className="px-2 py-2 text-right font-mono text-amber-100">
                        {(relay.i_hv_ref_amp?.[idx] ?? 0).toFixed(2)}
                      </td>
                      <td className="px-2 py-2 text-right font-mono text-cyan-100">
                        {(relay.i_lv_ref_amp?.[idx] ?? 0).toFixed(2)}
                      </td>
                      <td className="px-2 py-2 text-right font-mono text-slate-200">
                        {(relay.i_diff_amp?.[idx] ?? 0).toFixed(2)}
                      </td>
                      <td className="px-2 py-2 text-right font-mono text-slate-500">
                        {(relay.threshold_amp?.[idx] ?? 0).toFixed(2)}
                      </td>
                      <td className="px-2 py-2 text-center">
                        {relay.trip_phases[idx] ? (
                          <span className="font-bold text-red-400">TRIP</span>
                        ) : (
                          <span className="text-green-400">OK</span>
                        )}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>

            <div className="mt-3 text-[10px] text-slate-500">
              ค่า Raw คือกระแสดิบจากมิเตอร์ ส่วนค่า Ref คือกระแสหลังผ่าน current base และ turn ratio แล้ว เพื่อให้อยู่บนฐานเดียวกันก่อนคำนวณ Idiff
            </div>
          </div>

          {mode === "simulation" && (
            <div className="card p-4">
              <h3 className="mb-3 text-sm font-semibold text-slate-300">
                Fault Injection (Simulation)
              </h3>

              <div className="mb-3 grid grid-cols-2 gap-3">
                <div>
                  <div className="mb-1 text-[10px] uppercase text-slate-500">
                    Fault Phases
                  </div>
                  <div className="flex gap-2">
                    {["A", "B", "C"].map((ph) => (
                      <label
                        key={ph}
                        className="flex cursor-pointer items-center gap-1"
                      >
                        <input
                          type="checkbox"
                          checked={faultPhases.includes(ph)}
                          onChange={(e) => {
                            if (e.target.checked) {
                              setFaultPhases([...faultPhases, ph]);
                            } else {
                              setFaultPhases(faultPhases.filter((p) => p !== ph));
                            }
                          }}
                          className="accent-red-500"
                        />
                        <span className="text-xs text-slate-300">{ph}</span>
                      </label>
                    ))}
                  </div>
                </div>

                <div>
                  <div className="mb-1 text-[10px] uppercase text-slate-500">
                    ตัวคูณกระแส
                  </div>
                  <input
                    type="number"
                    step="0.5"
                    min="1"
                    max="20"
                    value={faultFactor}
                    onChange={(e) => setFaultFactor(parseFloat(e.target.value))}
                    className="w-full rounded-lg border border-slate-700 bg-slate-800 px-3 py-1.5 text-sm text-slate-200"
                  />
                </div>
              </div>

              <div className="flex gap-2">
                <button
                  onClick={injectFault}
                  disabled={faultActive}
                  className={`flex-1 cursor-pointer rounded-lg py-2.5 text-sm font-semibold transition-all ${
                    faultActive
                      ? "cursor-not-allowed bg-red-800 text-red-300"
                      : "bg-red-600 text-white hover:bg-red-500"
                  }`}
                >
                  {faultActive ? "Fault ทำงานอยู่" : "Inject Fault"}
                </button>
                <button
                  onClick={clearFault}
                  disabled={!faultActive}
                  className={`flex-1 cursor-pointer rounded-lg py-2.5 text-sm font-semibold transition-all ${
                    !faultActive
                      ? "cursor-not-allowed bg-slate-700 text-slate-500"
                      : "bg-green-600 text-white hover:bg-green-500"
                  }`}
                >
                  Clear Fault
                </button>
              </div>

              {faultActive && (
                <div className="mt-2 animate-pulse text-center text-[10px] text-red-400">
                  ระบบจำลอง fault ฝั่ง LV ด้วยตัวคูณ {faultFactor} ที่เฟส{" "}
                  {faultPhases.join(", ")}
                </div>
              )}
            </div>
          )}

          <div className="card p-4">
            <h3 className="mb-3 text-sm font-semibold text-slate-300">
              Trip History
            </h3>
            <div className="grid grid-cols-2 gap-3 text-xs">
              <div className="rounded-lg bg-slate-800/50 p-3">
                <div className="text-slate-500">จำนวนครั้งที่ Trip</div>
                <div className="mt-1 text-2xl font-bold text-red-400">
                  {relay.trip_count}
                </div>
              </div>
              <div className="rounded-lg bg-slate-800/50 p-3">
                <div className="text-slate-500">เฟสที่ Trip ล่าสุด</div>
                <div className="mt-1 text-lg font-bold text-slate-200">
                  {relay.last_trip_phases.length > 0
                    ? relay.last_trip_phases.join(", ")
                    : "-"}
                </div>
              </div>
              <div className="rounded-lg bg-slate-800/50 p-3">
                <div className="text-slate-500">เวลา Trip ล่าสุด</div>
                <div className="mt-1 text-sm font-mono text-slate-300">
                  {relay.trip_time
                    ? new Date(relay.trip_time * 1000).toLocaleString()
                    : "-"}
                </div>
              </div>
              <div className="rounded-lg bg-slate-800/50 p-3">
                <div className="text-slate-500">เวลา Reset ล่าสุด</div>
                <div className="mt-1 text-sm font-mono text-slate-300">
                  {relay.reset_time
                    ? new Date(relay.reset_time * 1000).toLocaleString()
                    : "-"}
                </div>
              </div>
            </div>
          </div>

          {relay.detection && (
            <div className="card p-4">
              <h3 className="mb-2 text-sm font-semibold text-slate-300">
                Detection Details
              </h3>
              <pre className="overflow-x-auto rounded-lg bg-slate-800/50 p-3 text-[10px] text-slate-400">
                {JSON.stringify(relay.detection, null, 2)}
              </pre>
            </div>
          )}
        </div>
      </div>
    </div>
  );
}
