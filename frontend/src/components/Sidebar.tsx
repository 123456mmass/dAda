"use client";

import React from "react";
import Link from "next/link";
import { usePathname } from "next/navigation";
import { useApp } from "@/context/AppContext";

const NAV_ITEMS = [
  { href: "/", label: "Meters", icon: "⚡" },
  { href: "/relay", label: "Relay", icon: "🛡" },
  { href: "/wave", label: "Waveforms", icon: "〰" },
  { href: "/config", label: "Settings", icon: "⚙" },
];

interface SidebarProps {
  theme: "dark" | "light";
  onToggleTheme: () => void;
}

export default function Sidebar({ theme, onToggleTheme }: SidebarProps) {
  const pathname = usePathname();
  const { data, wsConnected, backendUrl } = useApp();
  const relay = data?.relay;
  const mode = data?.mode || "simulation";
  const isTrip = relay?.status === "TRIP";

  const switchMode = async () => {
    const newMode = mode === "simulation" ? "real" : "simulation";
    try {
      const res = await fetch(`${backendUrl}/api/modbus/mode/${newMode}`, {
        method: "POST",
      });
      if (!res.ok) {
        const err = await res.json();
        alert(err.detail || "สลับโหมดไม่สำเร็จ");
      }
    } catch {
      alert("สลับโหมดไม่สำเร็จ");
    }
  };

  return (
    <aside style={{
      width: 200,
      minHeight: "100vh",
      background: "var(--header-bg)",
      borderRight: "1px solid var(--border-color)",
      backdropFilter: "blur(10px)",
      display: "flex",
      flexDirection: "column",
      padding: "0",
      position: "sticky",
      top: 0,
      flexShrink: 0,
      zIndex: 50,
    }}>

      {/* Logo / Title */}
      <div style={{
        padding: "18px 16px 14px",
        borderBottom: "1px solid var(--border-color)",
        display: "flex", alignItems: "center", gap: 10,
      }}>
        <div style={{
          width: 34, height: 34, borderRadius: 10, flexShrink: 0,
          background: "linear-gradient(135deg, #3b82f6, #06b6d4)",
          display: "flex", alignItems: "center", justifyContent: "center",
          color: "white", fontWeight: 900, fontSize: 11, letterSpacing: "-0.03em",
          boxShadow: "0 2px 8px rgba(59,130,246,0.4)",
        }}>
          87T
        </div>
        <div>
          <div style={{ fontSize: 11, fontWeight: 700, color: "var(--text-primary)", lineHeight: 1.2 }}>
            Differential Relay 87T
          </div>
          <div style={{ fontSize: 9, color: "var(--text-muted)", marginTop: 2 }}>
            {relay?.vector_family || "DD"} · Tap {relay?.tap_position || 1}
          </div>
        </div>
      </div>

      {/* Nav links */}
      <nav style={{ padding: "10px 8px", flex: 1, display: "flex", flexDirection: "column", gap: 2 }}>
        {NAV_ITEMS.map((item) => {
          const active = pathname === item.href;
          return (
            <Link
              key={item.href}
              href={item.href}
              style={{
                display: "flex", alignItems: "center", gap: 9,
                padding: "9px 12px", borderRadius: 9,
                fontSize: 12, fontWeight: active ? 600 : 400,
                color: active ? "var(--text-primary)" : "var(--text-muted)",
                background: active ? "var(--surface-chip)" : "transparent",
                boxShadow: active ? "var(--glow-blue)" : "none",
                textDecoration: "none",
                transition: "all .15s",
                borderLeft: active ? "2px solid var(--accent-blue)" : "2px solid transparent",
              }}
            >
              <span style={{ fontSize: 14 }}>{item.icon}</span>
              {item.label}
            </Link>
          );
        })}
      </nav>

      {/* Status / Controls */}
      <div style={{
        padding: "12px 10px",
        borderTop: "1px solid var(--border-color)",
        display: "flex", flexDirection: "column", gap: 8,
      }}>
        {/* Status badge */}
        <div style={{ display: "flex", alignItems: "center", gap: 6 }}>
          <span style={{
            display: "inline-flex", alignItems: "center", gap: 5,
            fontSize: 9, fontWeight: 700, letterSpacing: "0.05em", textTransform: "uppercase",
            padding: "3px 10px", borderRadius: 99,
            background: isTrip ? "rgba(239,68,68,0.15)" : "rgba(16,185,129,0.12)",
            border: `1px solid ${isTrip ? "rgba(239,68,68,0.35)" : "rgba(16,185,129,0.28)"}`,
            color: isTrip ? "var(--accent-red)" : "var(--accent-green)",
            animation: isTrip ? "pulse-red 1s ease-in-out infinite" : undefined,
            flex: 1, justifyContent: "center",
          }}>
            <span style={{ width: 6, height: 6, borderRadius: "50%", background: isTrip ? "var(--accent-red)" : "var(--accent-green)" }} />
            {relay?.status || "NORMAL"}
          </span>
        </div>

        {/* Mode + Phase row */}
        <div style={{ display: "flex", gap: 6 }}>
          <button
            onClick={switchMode}
            style={{
              flex: 1, fontSize: 9, padding: "4px 6px", borderRadius: 7, cursor: "pointer",
              fontWeight: 700, letterSpacing: "0.04em", border: "1px solid",
              background: mode === "real" ? "rgba(16,185,129,0.12)" : "rgba(139,92,246,0.12)",
              color: mode === "real" ? "var(--accent-green)" : "var(--accent-purple)",
              borderColor: mode === "real" ? "rgba(16,185,129,0.3)" : "rgba(139,92,246,0.3)",
            }}
          >
            {mode === "real" ? "⚡ REAL" : "SIM"}
          </button>
          <span style={{
            flex: 1, fontSize: 9, padding: "4px 6px", borderRadius: 7, textAlign: "center",
            fontWeight: 600, background: "var(--surface-chip)", color: "var(--text-muted)",
            border: "1px solid var(--border-color)", fontFamily: "monospace",
          }}>
            {relay?.system_phase || "IDLE"}
          </span>
        </div>

        {/* WS status */}
        <div style={{ display: "flex", alignItems: "center", gap: 6, paddingLeft: 2 }}>
          <span className={`status-dot ${wsConnected ? "connected" : "disconnected"}`} />
          <span style={{ fontSize: 9, color: "var(--text-muted)" }}>
            {wsConnected ? "เชื่อมต่อสด" : "ออฟไลน์"}
          </span>
        </div>

        {/* Theme toggle */}
        <button
          type="button"
          onClick={onToggleTheme}
          className="theme-toggle"
          style={{
            width: "100%", fontSize: 10, padding: "6px 0", borderRadius: 8,
            fontWeight: 600, cursor: "pointer", textAlign: "center",
          }}
        >
          {theme === "dark" ? "☀ Light Mode" : "☾ Dark Mode"}
        </button>
      </div>
    </aside>
  );
}
