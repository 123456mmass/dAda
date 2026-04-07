"use client";

import React, { useMemo } from "react";
import {
  Radar,
  RadarChart,
  PolarGrid,
  PolarAngleAxis,
  PolarRadiusAxis,
  ResponsiveContainer,
  Tooltip,
} from "recharts";
import { RelayData } from "@/context/AppContext";

interface Props {
  relay: RelayData;
}

function ArcGauge({
  value, max, label, color, tripped, idiff, threshold,
}: {
  value: number; max: number; label: string; color: string;
  tripped: boolean; idiff: number; threshold: number;
}) {
  const R = 52;
  const cx = 70, cy = 70;
  const startAngle = 210;
  const sweep = 240;

  const ratio = max > 0 ? Math.min(value / max, 1) : 0;
  const pct = Math.round(ratio * 100);

  const toRad = (deg: number) => (deg * Math.PI) / 180;
  const arcPath = (pct2: number, r: number) => {
    const start = startAngle;
    const angle = start + sweep * pct2;
    const x1 = cx + r * Math.cos(toRad(start));
    const y1 = cy + r * Math.sin(toRad(start));
    const x2 = cx + r * Math.cos(toRad(angle));
    const y2 = cy + r * Math.sin(toRad(angle));
    const largeArc = sweep * pct2 > 180 ? 1 : 0;
    return `M ${x1} ${y1} A ${r} ${r} 0 ${largeArc} 1 ${x2} ${y2}`;
  };

  const thresholdAngle = startAngle + sweep * Math.min(threshold / max, 1);
  const txRad = toRad(thresholdAngle);
  const txMark = {
    x: cx + (R + 9) * Math.cos(txRad),
    y: cy + (R + 9) * Math.sin(txRad),
  };

  const statusColor = tripped ? "#f87171" : ratio > 0.75 ? "#fbbf24" : "#34d399";

  return (
    <div style={{ textAlign: "center" }}>
      <svg width={140} height={130} viewBox="0 0 140 130">
        {/* Track */}
        <path
          d={arcPath(1, R)}
          fill="none"
          stroke="var(--border-color)"
          strokeWidth={10}
          strokeLinecap="round"
        />
        {/* Fill */}
        <path
          d={arcPath(ratio, R)}
          fill="none"
          stroke={tripped ? "#f87171" : ratio > 0.75 ? "#fbbf24" : color}
          strokeWidth={10}
          strokeLinecap="round"
        />
        {/* Threshold tick */}
        {threshold > 0 && max > 0 && (
          <circle cx={txMark.x} cy={txMark.y} r={4} fill="#10b981" opacity={0.85} />
        )}
        {/* Center label */}
        <text x={cx} y={cy - 8} textAnchor="middle" fill={statusColor} fontSize={16} fontWeight={700} fontFamily="monospace">
          {idiff.toFixed(2)}
        </text>
        <text x={cx} y={cy + 10} textAnchor="middle" fill="var(--text-muted)" fontSize={9} fontFamily="sans-serif">A</text>
        <text x={cx} y={cy + 24} textAnchor="middle" fill="var(--text-muted)" fontSize={8}>{pct}%</text>
        {/* Phase label */}
        <text x={cx} y={118} textAnchor="middle" fill={color} fontSize={13} fontWeight={800} letterSpacing={1}>
          {label}
        </text>
      </svg>
      <div style={{ marginTop: 2, fontSize: 10, color: "var(--text-muted)" }}>
        Threshold: <span style={{ color: "#10b981", fontFamily: "monospace" }}>{threshold.toFixed(3)} A</span>
      </div>
      <div style={{ marginTop: 3 }}>
        <span style={{
          fontSize: 9, fontWeight: 700, letterSpacing: "0.08em", textTransform: "uppercase",
          color: tripped ? "#f87171" : ratio > 0.75 ? "#fbbf24" : "#34d399",
          background: tripped ? "rgba(248,113,113,0.12)" : ratio > 0.75 ? "rgba(251,191,36,0.12)" : "rgba(52,211,153,0.12)",
          border: `1px solid ${tripped ? "rgba(248,113,113,0.3)" : ratio > 0.75 ? "rgba(251,191,36,0.3)" : "rgba(52,211,153,0.3)"}`,
          padding: "1px 8px", borderRadius: 99,
        }}>
          {tripped ? "⚠ TRIP" : ratio > 0.75 ? "⚡ ใกล้" : "✓ ปกติ"}
        </span>
      </div>
    </div>
  );
}

function CustomTooltip({ active, payload }: { active?: boolean; payload?: {name:string; value:number; color:string}[] }) {
  if (!active || !payload?.length) return null;
  return (
    <div style={{ background: "var(--tooltip-bg)", border: "1px solid var(--border-color)", borderRadius: 10, padding: "8px 14px", fontSize: 11, color: "var(--text-primary)" }}>
      {payload.map((p) => (
        <div key={p.name} style={{ color: p.color, fontFamily: "monospace", marginBottom: 2 }}>
          {p.name}: {Number(p.value).toFixed(3)} A
        </div>
      ))}
    </div>
  );
}

export default function TripChart({ relay }: Props) {
  const chartData = useMemo(() => {
    return [
      { phase: "A", i_diff: relay.i_diff_amp[0], threshold: relay.threshold_amp[0], tripped: relay.trip_phases[0] },
      { phase: "B", i_diff: relay.i_diff_amp[1], threshold: relay.threshold_amp[1], tripped: relay.trip_phases[1] },
      { phase: "C", i_diff: relay.i_diff_amp[2], threshold: relay.threshold_amp[2], tripped: relay.trip_phases[2] },
    ];
  }, [relay]);

  const radarData = useMemo(() => {
    return chartData.map(d => ({
      subject: `Phase ${d.phase}`,
      Idiff: d.threshold > 0 ? (d.i_diff / d.threshold) * 100 : 0,
      Threshold: 100,
      fullMark: 150,
    }));
  }, [chartData]);

  const maxAll = Math.max(...chartData.map(d => Math.max(d.i_diff, d.threshold)), 0.1);
  const isAnyTrip = relay.status === "TRIP";
  const PH_COLOR = ["#ef4444", "#fb923c", "#3b82f6"];

  return (
    <div className="card p-4">
      {/* Header */}
      <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", marginBottom: 16 }}>
        <div>
          <h3 style={{ fontSize: 13, fontWeight: 700, color: "var(--text-primary)" }}>
            Idiff — Differential Current Monitor
          </h3>
          <div style={{ fontSize: 11, color: "var(--text-muted)", marginTop: 3 }}>
            Arc gauge แต่ละเฟส + Radar เปรียบเทียบ Idiff กับ Threshold
          </div>
        </div>
        <span style={{
          fontSize: 10, fontWeight: 700, letterSpacing: "0.06em", textTransform: "uppercase",
          padding: "3px 12px", borderRadius: 99,
          background: isAnyTrip ? "rgba(248,113,113,0.12)" : "rgba(52,211,153,0.08)",
          border: `1px solid ${isAnyTrip ? "rgba(248,113,113,0.3)" : "rgba(52,211,153,0.2)"}`,
          color: isAnyTrip ? "#f87171" : "#34d399",
          animation: isAnyTrip ? "blink-trip 1s ease infinite" : undefined,
        }}>
          {isAnyTrip ? "⚠ TRIP ACTIVE" : "● NORMAL"}
        </span>
      </div>

      <div style={{ display: "grid", gridTemplateColumns: "repeat(3, 1fr) 1.2fr", gap: 16, alignItems: "center" }}>
        {chartData.map((d, i) => (
          <ArcGauge
            key={d.phase}
            value={d.i_diff}
            max={maxAll}
            label={`PHASE ${d.phase}`}
            color={PH_COLOR[i]}
            tripped={d.tripped}
            idiff={d.i_diff}
            threshold={d.threshold}
          />
        ))}

        {/* Radar chart */}
        <div style={{ height: 200 }}>
          <div style={{ fontSize: 9, color: "var(--text-muted)", textAlign: "center", marginBottom: 2, letterSpacing: "0.06em", textTransform: "uppercase" }}>
            Radar — Normalised (%)
          </div>
          <ResponsiveContainer width="100%" height="100%">
            <RadarChart data={radarData} margin={{ top: 10, right: 20, bottom: 10, left: 20 }}>
              <PolarGrid stroke="var(--border-color)" />
              <PolarAngleAxis
                dataKey="subject"
                tick={{ fill: "var(--text-muted)" as string, fontSize: 10 }}
              />
              <PolarRadiusAxis angle={30} domain={[0, 100]} tick={false} axisLine={false} />
              <Radar
                name="Idiff"
                dataKey="Idiff"
                stroke="#60a5fa"
                fill="#60a5fa"
                fillOpacity={0.25}
                dot={{ r: 3, fill: "#60a5fa" }}
              />
              <Radar
                name="Threshold"
                dataKey="Threshold"
                stroke="#10b981"
                fill="#10b981"
                fillOpacity={0.1}
                strokeDasharray="5 3"
                dot={false}
              />
              <Tooltip content={<CustomTooltip />} />
            </RadarChart>
          </ResponsiveContainer>
          <div style={{ display: "flex", justifyContent: "center", gap: 14, marginTop: 2 }}>
            <span style={{ fontSize: 9, color: "#60a5fa", display: "flex", alignItems: "center", gap: 4 }}>
              <span style={{ width: 14, height: 2, background: "#60a5fa", borderRadius: 1, display: "inline-block" }} /> Idiff
            </span>
            <span style={{ fontSize: 9, color: "#10b981", display: "flex", alignItems: "center", gap: 4 }}>
              <span style={{ width: 14, height: 2, background: "#10b981", borderRadius: 1, display: "inline-block" }} /> Threshold
            </span>
          </div>
        </div>
      </div>

      {/* Phase status bar */}
      <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr 1fr", gap: 8, marginTop: 14 }}>
        {chartData.map((d, idx) => {
          return (
            <div key={d.phase} style={{
              padding: "10px 14px", borderRadius: 10,
              background: d.tripped ? "rgba(248,113,113,0.07)" : "var(--surface-soft)",
              border: `1px solid ${d.tripped ? "rgba(248,113,113,0.3)" : "var(--border-color)"}`,
            }}>
              <div style={{ display: "flex", justifyContent: "space-between", marginBottom: 6 }}>
                <span style={{ fontWeight: 700, fontSize: 12, color: PH_COLOR[idx] }}>Phase {d.phase}</span>
                <span style={{ fontFamily: "monospace", fontWeight: 700, fontSize: 12, color: d.tripped ? "#f87171" : "var(--text-primary)" }}>
                  {d.i_diff.toFixed(3)} A
                </span>
              </div>
              <div style={{ height: 3, borderRadius: 99, background: "var(--border-color)", overflow: "hidden" }}>
                <div style={{
                  height: "100%", width: `${Math.min((d.i_diff / d.threshold) * 100, 100)}%`,
                  background: d.tripped ? "#f87171" : (d.threshold > 0 && d.i_diff / d.threshold > 0.75) ? "#fbbf24" : PH_COLOR[idx],
                  borderRadius: 99, transition: "width .4s ease",
                }} />
              </div>
              <div style={{ display: "flex", justifyContent: "space-between", marginTop: 4, fontSize: 9, color: "var(--text-muted)" }}>
                <span>{Math.round((d.i_diff / d.threshold) * 100)}% of threshold</span>
                <span>T: {d.threshold.toFixed(3)} A</span>
              </div>
            </div>
          );
        })}
      </div>
    </div>
  );
}
