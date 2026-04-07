"use client";

import React from "react";
import { MeterData, RelayData } from "@/context/AppContext";

interface Props {
  title: string;
  side: "HV" | "LV";
  address: number;
  data: MeterData;
  relay?: RelayData | null;
}

function SparkBar({ value, max, color }: { value: number; max: number; color: string }) {
  const pct = max > 0 ? Math.min((value / max) * 100, 100) : 0;
  return (
    <div style={{ height: 3, background: "var(--border-color)", borderRadius: 99, overflow: "hidden", marginTop: 4, opacity: 0.6 }}>
      <div style={{
        height: "100%", width: `${pct}%`, borderRadius: 99,
        background: color, transition: "width .4s ease",
      }} />
    </div>
  );
}

function PhaseCol({
  phase, voltage, current, normalized, phColor,
}: {
  phase: string; voltage: number; current: number; normalized: number; phColor: string;
}) {
  const maxV = 480, maxI = 50;
  return (
    <div style={{
      flex: 1, padding: "12px 10px",
      borderRight: "1px solid var(--border-color)",
      display: "flex", flexDirection: "column", gap: 12,
    }}>
      {/* Phase badge */}
      <div style={{ textAlign: "center" }}>
        <span style={{
          fontSize: 9, fontWeight: 800, letterSpacing: "0.12em", textTransform: "uppercase",
          color: phColor, border: `1px solid ${phColor}44`,
          padding: "2px 8px", borderRadius: 99,
          background: `${phColor}18`,
        }}>
          {phase}
        </span>
      </div>

      {/* Voltage LL */}
      <div>
        <div style={{ fontSize: 9, color: "var(--text-secondary)", textTransform: "uppercase", letterSpacing: "0.08em", marginBottom: 3, opacity: 0.8 }}>
          Voltage LL
        </div>
        <div style={{ fontSize: 18, fontWeight: 800, color: phColor, letterSpacing: "-0.03em", fontVariantNumeric: "tabular-nums", lineHeight: 1 }}>
          {voltage.toFixed(1)}
        </div>
        <div style={{ fontSize: 9, color: "var(--text-secondary)", marginTop: 1, opacity: 0.6 }}>V</div>
        <SparkBar value={voltage} max={maxV} color={phColor} />
      </div>

      {/* Current raw */}
      <div>
        <div style={{ fontSize: 9, color: "var(--text-secondary)", textTransform: "uppercase", letterSpacing: "0.08em", marginBottom: 3, opacity: 0.8 }}>
          I Raw
        </div>
        <div style={{ fontSize: 15, fontWeight: 700, color: "var(--text-secondary)", letterSpacing: "-0.02em", fontVariantNumeric: "tabular-nums", lineHeight: 1 }}>
          {current.toFixed(2)}
        </div>
        <div style={{ fontSize: 9, color: "var(--text-secondary)", marginTop: 1, opacity: 0.6 }}>A</div>
        <SparkBar value={current} max={maxI} color="var(--text-muted)" />
      </div>

      {/* Normalized */}
      <div>
        <div style={{ fontSize: 9, color: "var(--text-secondary)", textTransform: "uppercase", letterSpacing: "0.08em", marginBottom: 3, opacity: 0.8 }}>
          I Ref
        </div>
        <div style={{ fontSize: 13, fontWeight: 700, color: phColor, opacity: 0.95, letterSpacing: "-0.01em", fontVariantNumeric: "tabular-nums", lineHeight: 1 }}>
          {normalized.toFixed(3)}
        </div>
        <div style={{ fontSize: 9, color: "var(--text-secondary)", marginTop: 1, opacity: 0.6 }}>A</div>
        <SparkBar value={normalized} max={maxI} color={phColor} />
      </div>
    </div>
  );
}

export default function MeterCard({ title, side, address, data, relay }: Props) {
  const isHV = side === "HV";
  const accentArr = isHV ? ["var(--accent-amber)", "#f59e0b"] : ["var(--accent-cyan)", "#06b6d4"];
  const accent = accentArr[0];
  const accentHex = accentArr[1];
  const normCurrent = isHV ? relay?.i_hv_ref_amp ?? [0, 0, 0] : relay?.i_lv_ref_amp ?? [0, 0, 0];

  const PH_HEX = ["#ef4444", "#f59e0b", "#3b82f6"] as const;
  const voltages = [data.voltage_ll.ab, data.voltage_ll.bc, data.voltage_ll.ca];
  const currents = [data.current.a, data.current.b, data.current.c];
  const phases = ["A", "B", "C"];

  return (
    <div
      className={!data.connected ? "opacity-80 grayscale-[0.2]" : ""}
      style={{
        background: "var(--bg-card)",
        border: `1px solid var(--border-color)`,
        borderRadius: 16, overflow: "hidden",
        transition: "border-color .2s, background .25s",
        borderTop: `2px solid ${accentHex}`,
      }}
    >
      {/* Header */}
      <div style={{
        display: "flex", alignItems: "center", justifyContent: "space-between",
        padding: "10px 16px",
        background: "var(--surface-soft)",
        borderBottom: "1px solid var(--border-color)",
      }}>
        <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
          <span className={`status-dot ${data.connected ? "connected" : "disconnected"}`} />
          <span style={{ fontSize: 12, fontWeight: 700, color: accent, letterSpacing: "-0.01em" }}>
            {title}
          </span>
        </div>
        <div style={{ display: "flex", alignItems: "center", gap: 10 }}>
          {data.connected ? (
            <span style={{
              fontSize: 9, color: "var(--accent-green)",
              background: "rgba(16,185,129,0.1)", border: "1px solid rgba(16,185,129,0.25)",
              padding: "1px 8px", borderRadius: 99, fontWeight: 700, letterSpacing: "0.06em",
            }}>
              ● LIVE
            </span>
          ) : (
            <span style={{
              fontSize: 9, color: "var(--text-muted)",
              background: "var(--surface-chip)", border: "1px solid var(--border-color)",
              padding: "1px 8px", borderRadius: 99, fontWeight: 700, letterSpacing: "0.06em",
            }}>
              ○ OFFLINE
            </span>
          )}
          <span style={{ fontSize: 9, color: "var(--text-muted)", fontFamily: "monospace" }}>
            Addr: {address}
          </span>
        </div>
      </div>

      {/* Hero avg voltage */}
      <div style={{
        padding: "14px 16px 10px",
        borderBottom: "1px solid var(--border-color)",
      }}>
        <div style={{ fontSize: 9, color: "var(--text-muted)", textTransform: "uppercase", letterSpacing: "0.1em", marginBottom: 4 }}>
          Avg Voltage L-L
        </div>
        <div style={{ display: "flex", alignItems: "baseline", gap: 6 }}>
          <span style={{ fontSize: 36, fontWeight: 900, color: accent, letterSpacing: "-0.04em", lineHeight: 1, fontVariantNumeric: "tabular-nums" }}>
            {data.voltage_ll.avg.toFixed(1)}
          </span>
          <span style={{ fontSize: 13, color: "var(--text-secondary)", fontWeight: 500, opacity: 0.8 }}>V</span>
          <span style={{ marginLeft: "auto", fontSize: 11, fontFamily: "monospace", color: "var(--text-secondary)", fontWeight: 600, opacity: 0.8 }}>
            {data.frequency.toFixed(2)} Hz
          </span>
        </div>
      </div>

      {/* Phase columns */}
      <div style={{ display: "flex", borderBottom: "1px solid var(--border-color)" }}>
        {phases.map((ph, i) => (
          <PhaseCol
            key={ph}
            phase={ph}
            voltage={voltages[i]}
            current={currents[i]}
            normalized={normCurrent[i] ?? 0}
            phColor={PH_HEX[i]}
          />
        ))}
      </div>

      {/* Footer */}
      <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr 1fr" }}>
        <div style={{ padding: "10px 14px", borderRight: "1px solid var(--border-color)" }}>
          <div style={{ fontSize: 9, color: "var(--text-secondary)", textTransform: "uppercase", letterSpacing: "0.08em", marginBottom: 3, opacity: 0.8 }}>
            Neutral I_N
          </div>
          <div style={{ fontSize: 13, fontWeight: 700, color: "var(--phase-n)", fontVariantNumeric: "tabular-nums" }}>
            {data.current.n.toFixed(3)} <span style={{ fontSize: 9, color: "var(--text-secondary)", opacity: 0.6 }}>A</span>
          </div>
        </div>
        <div style={{ padding: "10px 14px", borderRight: "1px solid var(--border-color)" }}>
          <div style={{ fontSize: 9, color: "var(--text-secondary)", textTransform: "uppercase", letterSpacing: "0.08em", marginBottom: 3, opacity: 0.8 }}>
            Power (P)
          </div>
          <div style={{ fontSize: 13, fontWeight: 700, color: "var(--text-secondary)", fontVariantNumeric: "tabular-nums" }}>
            {(data.power.p_total / 1000).toFixed(2)} <span style={{ fontSize: 9, color: "var(--text-secondary)", opacity: 0.6 }}>kW</span>
          </div>
        </div>
        <div style={{ padding: "10px 14px" }}>
          <div style={{ fontSize: 9, color: "var(--text-secondary)", textTransform: "uppercase", letterSpacing: "0.08em", marginBottom: 3, opacity: 0.8 }}>
            Avg I
          </div>
          <div style={{ fontSize: 13, fontWeight: 700, color: "var(--text-secondary)", fontVariantNumeric: "tabular-nums" }}>
            {data.current.avg.toFixed(3)} <span style={{ fontSize: 9, color: "var(--text-secondary)", opacity: 0.6 }}>A</span>
          </div>
        </div>
      </div>
    </div>
  );
}
