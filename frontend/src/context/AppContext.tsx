"use client";

import React, {
  createContext,
  useContext,
  useEffect,
  useState,
  useRef,
  ReactNode,
} from "react";

// ── Types ──
export interface MeterData {
  connected: boolean;
  timestamp: number;
  current: { a: number; b: number; c: number; n: number; avg: number };
  voltage_ll: { ab: number; bc: number; ca: number; avg: number };
  voltage_ln: { an: number; bn: number; cn: number; avg: number };
  power_factor: { a: number; b: number; c: number; total: number };
  power: { p_total: number; q_total: number; s_total: number };
  frequency: number;
  phase_angles: {
    v1: number; v2: number; v3: number;
    i1: number; i2: number; i3: number;
  };
}

export interface RelayData {
  system_phase: string;
  status: string;
  i_diff: number[];
  i_bias: number[];
  trip_phases: boolean[];
  thresholds: number[];
  vector_group: string;
  vector_family: string;
  compensation_group: string;
  tap_position: number;
  trip_time: number | null;
  reset_time: number | null;
  trip_count: number;
  last_trip_phases: string[];
  i_hv_pu: number[];
  i_lv_pu: number[];
  i_lv_comp: number[];
  // Ampere values
  i_hv_amp: number[];
  i_lv_amp: number[];
  i_hv_ref_amp: number[];
  i_lv_ref_amp: number[];
  i_diff_amp: number[];
  i_bias_amp: number[];
  threshold_amp: number[];
  inrush_block_active: boolean;
  inrush_block_remaining_ms: number;
  detection: Record<string, unknown> | null;
}

export interface WaveformSide {
  voltage_ll: { ab: number[]; bc: number[]; ca: number[] };
  current_l: { a: number[]; b: number[]; c: number[] };
  current_n: number[];
}

export interface WaveformData {
  time_ms: number[];
  hv: WaveformSide;
  lv: WaveformSide;
}

export interface RealtimePayload {
  timestamp: number;
  mode: "simulation" | "real";
  port: string | null;
  meters: { hv: MeterData; lv: MeterData };
  relay: RelayData;
  waveforms: WaveformData;
}

interface AppContextType {
  data: RealtimePayload | null;
  wsConnected: boolean;
  backendUrl: string;
  setBackendUrl: (url: string) => void;
}

// ── Default values ──
const AppContext = createContext<AppContextType>({
  data: null,
  wsConnected: false,
  backendUrl: "http://localhost:8000",
  setBackendUrl: () => {},
});

export const useApp = () => useContext(AppContext);

export function AppProvider({ children }: { children: ReactNode }) {
  const [data, setData] = useState<RealtimePayload | null>(null);
  const [wsConnected, setWsConnected] = useState(false);
  const [backendUrl, setBackendUrl] = useState("http://localhost:8000");
  const wsRef = useRef<WebSocket | null>(null);
  const reconnectTimeout = useRef<NodeJS.Timeout | null>(null);

  useEffect(() => {
    let active = true;

    const connect = () => {
      const wsUrl = backendUrl.replace(/^http/, "ws") + "/ws/realtime";

      try {
        const ws = new WebSocket(wsUrl);
        wsRef.current = ws;

        ws.onopen = () => {
          setWsConnected(true);
          console.log("WebSocket connected");
        };

        ws.onmessage = (event) => {
          try {
            const payload: RealtimePayload = JSON.parse(event.data);
            setData(payload);
          } catch (e) {
            console.error("WS parse error:", e);
          }
        };

        ws.onclose = () => {
          setWsConnected(false);
          if (!active) return;
          console.log("WebSocket disconnected, reconnecting in 2s...");
          reconnectTimeout.current = setTimeout(connect, 2000);
        };

        ws.onerror = (err) => {
          console.error("WebSocket error:", err);
          ws.close();
        };
      } catch (e) {
        console.error("WebSocket connect failed:", e);
        if (!active) return;
        reconnectTimeout.current = setTimeout(connect, 3000);
      }
    };

    connect();
    return () => {
      active = false;
      if (reconnectTimeout.current) clearTimeout(reconnectTimeout.current);
      if (wsRef.current) wsRef.current.close();
    };
  }, [backendUrl]);

  return (
    <AppContext.Provider value={{ data, wsConnected, backendUrl, setBackendUrl }}>
      {children}
    </AppContext.Provider>
  );
}
