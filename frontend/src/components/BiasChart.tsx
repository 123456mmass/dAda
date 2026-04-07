"use client";

import React, { useEffect, useState, useMemo } from "react";
import {
  ComposedChart,
  Area,
  Line,
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip,
  ResponsiveContainer,
  ReferenceDot,
  Label,
} from "recharts";
import { RelayData } from "@/context/AppContext";

interface BiasPoint {
  bias: number;
  threshold: number;
  operate?: number;
}

interface CurveParams {
  i_pickup: number;
  slope1: number;
  slope2: number;
  bias_breakpoint: number;
}

interface BiasChartProps {
  relay: RelayData;
}

const PHASE_COLORS = ["#ef4444", "#f59e0b", "#3b82f6"];
const PHASE_LABELS = ["A", "B", "C"];

export default function BiasChart({ relay }: BiasChartProps) {
  const [curve, setCurve] = useState<BiasPoint[]>([]);
  const [params, setParams] = useState<CurveParams | null>(null);

  useEffect(() => {
    async function fetchCurve() {
      try {
        const res = await fetch("http://localhost:8000/api/relay/bias-characteristic");
        const data = await res.json();
        if (data.curve) {
          const maxIdiff = Math.max(...data.curve.map((p: any) => p.threshold)) * 2;
          const points = data.curve.map((p: any) => ({
            ...p,
            operate: maxIdiff,
          }));
          setCurve(points);
          setParams(data.params);
        }
      } catch (err) {
        console.error("Failed to fetch bias curve:", err);
      }
    }
    fetchCurve();
  }, [relay.vector_group, relay.tap_position]);

  // Calculate axis domain to include both the curve AND the phase operating points
  const { xDomain, yDomain } = useMemo(() => {
    const maxBias = Math.max(...relay.i_bias_amp, curve.length > 0 ? curve[curve.length - 1].bias : 0, 10);
    const maxDiff = Math.max(...relay.i_diff_amp, curve.length > 0 ? Math.max(...curve.map(c => c.threshold)) : 0, 1);
    return {
      xDomain: [0, maxBias * 1.2] as [number, number],
      yDomain: [0, maxDiff * 1.3] as [number, number],
    };
  }, [curve, relay.i_bias_amp, relay.i_diff_amp]);

  return (
    <div className="card w-full p-4 overflow-hidden relative" style={{ height: 400, display: "flex", flexDirection: "column" }}>
      {/* Header */}
      <div style={{ marginBottom: 12, display: "flex", alignItems: "center", justifyContent: "space-between", flexShrink: 0 }}>
        <div>
          <h3 style={{ fontSize: 13, fontWeight: 700, color: "var(--text-primary)" }}>Biased Differential Characteristic</h3>
          <p style={{ fontSize: 10, color: "var(--text-muted)", textTransform: "uppercase", letterSpacing: "0.05em", marginTop: 2 }}>I-diff vs I-bias (Amperes)</p>
        </div>
        {params && (
          <div style={{ display: "flex", gap: 12, fontSize: 10, background: "rgba(15,23,42,0.5)", padding: "4px 12px", borderRadius: 99, border: "1px solid var(--border-color)" }}>
            <span style={{ color: "var(--text-muted)" }}>Pickup: <span style={{ color: "var(--accent-blue)", fontWeight: 700 }}>{params.i_pickup}A</span></span>
            <span style={{ color: "var(--text-muted)" }}>S1: <span style={{ color: "var(--accent-blue)", fontWeight: 700 }}>{(params.slope1 * 100).toFixed(0)}%</span></span>
            <span style={{ color: "var(--text-muted)" }}>S2: <span style={{ color: "var(--accent-blue)", fontWeight: 700 }}>{(params.slope2 * 100).toFixed(0)}%</span></span>
          </div>
        )}
      </div>

      {/* Chart */}
      <div style={{ flex: 1, width: "100%", minHeight: 0 }}>
        <ResponsiveContainer width="100%" height="100%">
          <ComposedChart data={curve} margin={{ top: 10, right: 40, left: 10, bottom: 20 }}>
            <CartesianGrid strokeDasharray="3 3" vertical={false} stroke="rgba(255,255,255,0.05)" />

            <XAxis
              dataKey="bias"
              type="number"
              domain={xDomain}
              tick={{ fill: "var(--text-muted)", fontSize: 10 }}
              stroke="var(--border-color)"
            >
              <Label value="I-bias (A)" offset={-10} position="insideBottom" fill="var(--text-muted)" fontSize={10} fontWeight={600} />
            </XAxis>

            <YAxis
              type="number"
              domain={yDomain}
              tick={{ fill: "var(--text-muted)", fontSize: 10 }}
              stroke="var(--border-color)"
            >
              <Label value="I-diff (A)" angle={-90} position="insideLeft" offset={10} fill="var(--text-muted)" fontSize={10} fontWeight={600} />
            </YAxis>

            <Tooltip
              content={({ active, payload }) => {
                if (active && payload && payload.length) {
                  const d = payload[0].payload;
                  return (
                    <div style={{ background: "var(--tooltip-bg)", border: "1px solid var(--border-color)", borderRadius: 10, padding: "8px 14px", fontSize: 11 }}>
                      <p style={{ fontSize: 11, fontWeight: 700, color: "var(--text-primary)", marginBottom: 4 }}>Bias: {d.bias?.toFixed(3)}A</p>
                      <p style={{ color: "var(--text-muted)" }}>Trip threshold: <span style={{ color: "var(--accent-blue)", fontWeight: 700 }}>{d.threshold?.toFixed(3)}A</span></p>
                    </div>
                  );
                }
                return null;
              }}
            />

            {/* Red shading above the curve (Operate zone) */}
            <Area
              type="monotone"
              dataKey="operate"
              stroke="none"
              fill="rgba(239, 68, 68, 0.06)"
              isAnimationActive={false}
            />

            {/* Trip Boundary Curve */}
            <Line
              type="monotone"
              dataKey="threshold"
              stroke="var(--accent-blue)"
              strokeWidth={2.5}
              dot={false}
              isAnimationActive={false}
              name="Trip Boundary"
            />

            {/* Phase Operating Points using ReferenceDot */}
            {relay.i_bias_amp.map((bias, i) => {
              const idiff = relay.i_diff_amp[i];
              const tripped = relay.trip_phases[i];
              return (
                <ReferenceDot
                  key={`phase-${PHASE_LABELS[i]}`}
                  x={bias}
                  y={idiff}
                  r={7}
                  fill={PHASE_COLORS[i]}
                  stroke={tripped ? "#ffffff" : "transparent"}
                  strokeWidth={2}
                  label={{
                    value: PHASE_LABELS[i],
                    position: "top",
                    fill: PHASE_COLORS[i],
                    fontSize: 10,
                    fontWeight: 700,
                  }}
                />
              );
            })}
          </ComposedChart>
        </ResponsiveContainer>
      </div>

      {/* Legend */}
      <div style={{ display: "flex", justifyContent: "flex-end", gap: 16, marginTop: 6 }}>
        {PHASE_LABELS.map((ph, i) => (
          <div key={ph} style={{ display: "flex", alignItems: "center", gap: 6 }}>
            <div style={{ height: 8, width: 8, borderRadius: "50%", background: PHASE_COLORS[i] }} />
            <span style={{ fontSize: 9, fontWeight: 700, color: "var(--text-muted)", textTransform: "uppercase" }}>Phase {ph}</span>
          </div>
        ))}
        <div style={{ display: "flex", alignItems: "center", gap: 6 }}>
          <div style={{ height: 2, width: 16, background: "var(--accent-blue)" }} />
          <span style={{ fontSize: 9, fontWeight: 700, color: "var(--text-muted)", textTransform: "uppercase" }}>Trip Boundary</span>
        </div>
      </div>
    </div>
  );
}
