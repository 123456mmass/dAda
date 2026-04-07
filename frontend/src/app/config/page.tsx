"use client";

import React, { useCallback, useEffect, useState } from "react";
import { useApp } from "@/context/AppContext";

const VECTOR_GROUP_OPTIONS = [
  "Dd0",
  "Dd6",
  "Yy0",
  "Yy6",
  "YNyn0",
  "Dy1",
  "Dy5",
  "Dy7",
  "Dy11",
  "Dyn1",
  "Dyn11",
  "YNy0",
  "Yd1",
  "Yd5",
  "Yd7",
  "Yd11",
  "YNd1",
  "YNd11",
];

interface ConfigData {
  transformer: {
    equipment_mode: string;
    kva: number;
    detection_mode: string;
    vector_group: string;
    tap_position: number;
    autotransformer_turns_ratio: number;
    v_hv: number;
    v_lv: number;
    i_rated_hv: number;
    i_rated_lv: number;
    nameplate_i_hv: number;
    nameplate_i_lv: number;
    ct_ratio_hv: number;
    ct_ratio_lv: number;
    current_base_hv_secondary: number;
    current_base_lv_secondary: number;
    phase_shift_deg: number;
  };
  modbus: {
    port: string;
    baudrate: number;
    parity: string;
    stopbits: number;
    bytesize: number;
    timeout: number;
    poll_interval_ms: number;
    hv_meter_address: number;
    lv_meter_address: number;
  };
  relay: {
    i_pickup: number;
    slope1: number;
    slope2: number;
    bias_breakpoint: number;
    inrush_block_ms: number;
    trip_enabled: boolean;
    auto_reset: boolean;
    reset_delay_ms: number;
    filter_zero_seq_hv: boolean;
    filter_zero_seq_lv: boolean;
  };
}

function SettingsContent() {
  const { data, backendUrl } = useApp();
  const [config, setConfig] = useState<ConfigData | null>(null);
  const [ports, setPorts] = useState<string[]>([]);
  const [drafts, setDrafts] = useState<Record<string, string>>({});
  const [detecting, setDetecting] = useState(false);
  const [connectingState, setConnectingState] = useState<null | "auto" | "manual">(null);
  const [savingAll, setSavingAll] = useState(false);
  const [saved, setSaved] = useState("");
  const [presetNotes, setPresetNotes] = useState<string[]>([]);

  const mode = data?.mode || "simulation";

  const fetchConfig = useCallback(async () => {
    try {
      const res = await fetch(`${backendUrl}/api/relay/config`);
      setConfig(await res.json());
    } catch {}
  }, [backendUrl]);

  const fetchPorts = useCallback(async () => {
    try {
      const res = await fetch(`${backendUrl}/api/modbus/ports`);
      const d = await res.json();
      setPorts(d.ports || []);
    } catch {}
  }, [backendUrl]);

  useEffect(() => {
    let active = true;
    const load = async () => {
      try {
        const [configRes, portsRes] = await Promise.all([
          fetch(`${backendUrl}/api/relay/config`),
          fetch(`${backendUrl}/api/modbus/ports`),
        ]);
        const [configData, portsData] = await Promise.all([
          configRes.json(),
          portsRes.json(),
        ]);
        if (!active) return;
        setConfig(configData);
        setPorts(portsData.ports || []);
      } catch {}
    };

    void load();
    return () => {
      active = false;
    };
  }, [backendUrl]);

  useEffect(() => {
    if (!config) return;
    setDrafts({
      port: config.modbus.port || "auto",
      baudrate: String(config.modbus.baudrate ?? ""),
      parity: config.modbus.parity || "N",
      i_pickup_amp: (config.relay.i_pickup || 0).toFixed(2),
      inrush_block_ms: String(config.relay.inrush_block_ms ?? 700),
      reset_delay_ms: String(config.relay.reset_delay_ms ?? 5000),
      slope1: (config.relay.slope1 ?? 0.25).toFixed(2),
      slope2: (config.relay.slope2 ?? 0.50).toFixed(2),
      bias_breakpoint: (config.relay.bias_breakpoint ?? 1.0).toFixed(2),
    });
  }, [config]);

  const flash = (msg: string) => {
    setSaved(msg);
    setTimeout(() => setSaved(""), 2000);
  };

  const setDraftValue = (field: string, value: string) => {
    setDrafts((prev) => ({ ...prev, [field]: value }));
  };

  const parseIntegerDraft = (key: string, fallback: number, minimum?: number) => {
    const raw = drafts[key] ?? "";
    const parsed = raw.trim() === "" ? fallback : parseInt(raw, 10);
    if (Number.isNaN(parsed)) return fallback;
    return minimum !== undefined ? Math.max(minimum, parsed) : parsed;
  };

  const parseFloatDraft = (key: string, fallback: number, minimum?: number) => {
    const raw = drafts[key] ?? "";
    const parsed = raw.trim() === "" ? fallback : parseFloat(raw);
    if (Number.isNaN(parsed)) return fallback;
    return minimum !== undefined ? Math.max(minimum, parsed) : parsed;
  };

  const updateTransformer = async (field: string, value: string | number) => {
    try {
      await fetch(`${backendUrl}/api/relay/config/transformer`, {
        method: "PUT",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ [field]: value }),
      });
      await fetchConfig();
      flash("บันทึกแล้ว");
    } catch {}
  };

  const updateRelay = async (field: string, value: number | boolean) => {
    try {
      await fetch(`${backendUrl}/api/relay/config/relay`, {
        method: "PUT",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ [field]: value }),
      });
      await fetchConfig();
      flash("บันทึกแล้ว");
    } catch {}
  };

  const updateModbus = async (field: string, value: string | number) => {
    try {
      await fetch(`${backendUrl}/api/modbus/config`, {
        method: "PUT",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ [field]: value }),
      });
      await fetchConfig();
      flash("บันทึกแล้ว");
    } catch {}
  };

  const switchMode = async (newMode: string) => {
    try {
      const res = await fetch(`${backendUrl}/api/modbus/mode/${newMode}`, {
        method: "POST",
      });
      if (!res.ok) {
        const err = await res.json();
        alert(err.detail || "สลับโหมดไม่สำเร็จ");
      } else {
        flash(`สลับเป็นโหมด ${newMode}`);
      }
    } catch {}
  };

  const runConnect = async (
    body: Record<string, string | undefined>,
    kind: "auto" | "manual",
    successMessage: string
  ) => {
    setConnectingState(kind);
    try {
      const res = await fetch(`${backendUrl}/api/modbus/connect`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(body),
      });
      if (!res.ok) {
        const err = await res.json().catch(() => ({}));
        alert(err.detail || "เชื่อมต่อไม่สำเร็จ");
        return;
      }
      await Promise.all([fetchConfig(), fetchPorts()]);
      flash(successMessage);
    } catch {
      alert("เชื่อมต่อไม่สำเร็จ");
    } finally {
      setConnectingState(null);
    }
  };

  const connectPorts = async (portArg?: string) => {
    const nextPort = portArg || drafts.port || config?.modbus.port || "auto";
    const nextBaudrate = parseInt(drafts.baudrate || String(config?.modbus.baudrate || "38400"), 10);
    const nextParity = drafts.parity || config?.modbus.parity || "N";

    await fetch(`${backendUrl}/api/modbus/config`, {
      method: "PUT",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        port: nextPort,
        baudrate: Number.isNaN(nextBaudrate) ? (config?.modbus.baudrate || 38400) : nextBaudrate,
        parity: nextParity,
      }),
    });

    await runConnect(
      { port: nextPort },
      "manual",
      `เชื่อมต่อ ${nextPort} แล้ว`
    );
  };

  const autoPairMeters = async () => {
    await runConnect(
      { port: "auto" },
      "auto",
      "จับคู่มิเตอร์ #1 และ #2 อัตโนมัติแล้ว"
    );
  };

  const autoDetect = async () => {
    setDetecting(true);
    try {
      const res = await fetch(`${backendUrl}/api/relay/detect-vector-group`, {
        method: "POST",
      });
      const result = await res.json();
      if (result.detected) {
        await fetchConfig();
        flash(`Detected: ${result.vector_group} / Tap ${result.tap_position}`);
      } else {
        alert(`ตรวจจับไม่สำเร็จ: ${result.reason}`);
      }
    } catch {}
    setDetecting(false);
  };

  const reDetect = async () => {
    try {
      await fetch(`${backendUrl}/api/relay/re-detect`, { method: "POST" });
      flash("สั่งตรวจจับใหม่แล้ว");
    } catch {}
  };

  const applyAutotransformerPreset = async () => {
    try {
      const res = await fetch(
        `${backendUrl}/api/relay/presets/autotransformer-test`,
        { method: "POST" }
      );
      const payload = await res.json();
      setPresetNotes(payload.notes || []);
      await fetchConfig();
      flash("ใช้ preset ของ autotransformer แล้ว");
    } catch {}
  };

  const saveAllSettings = async () => {
    if (!config) return;

    const nextBaurdate = parseIntegerDraft("baudrate", config.modbus.baudrate, 1);
    const nextPickupAmp = parseFloatDraft(
      "i_pickup_amp",
      config.relay.i_pickup || 0,
      0
    );
    const nextInrushBlock = parseIntegerDraft(
      "inrush_block_ms",
      config.relay.inrush_block_ms ?? 700,
      0
    );
    const nextResetDelay = parseIntegerDraft(
      "reset_delay_ms",
      config.relay.reset_delay_ms ?? 5000,
      0
    );
    const nextSlope1 = parseFloatDraft("slope1", config.relay.slope1 ?? 0.25, 0);
    const nextSlope2 = parseFloatDraft("slope2", config.relay.slope2 ?? 0.50, 0);
    const nextBiasBreakpoint = parseFloatDraft("bias_breakpoint", config.relay.bias_breakpoint ?? 1.0, 0);

    setSavingAll(true);
    try {
      await Promise.all([
        fetch(`${backendUrl}/api/modbus/config`, {
          method: "PUT",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({
            port: drafts.port || config.modbus.port || "auto",
            baudrate: nextBaurdate,
            parity: drafts.parity || config.modbus.parity || "N",
          }),
        }),
        fetch(`${backendUrl}/api/relay/config/transformer`, {
          method: "PUT",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({
            equipment_mode: config.transformer.equipment_mode,
            detection_mode: config.transformer.detection_mode,
            vector_group: config.transformer.vector_group,
            tap_position: config.transformer.tap_position,
            autotransformer_turns_ratio: config.transformer.autotransformer_turns_ratio,
          }),
        }),
        fetch(`${backendUrl}/api/relay/config/relay`, {
          method: "PUT",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({
            i_pickup: nextPickupAmp,
            inrush_block_ms: nextInrushBlock,
            reset_delay_ms: nextResetDelay,
            slope1: nextSlope1,
            slope2: nextSlope2,
            bias_breakpoint: nextBiasBreakpoint,
            trip_enabled: config.relay.trip_enabled,
            auto_reset: config.relay.auto_reset,
            filter_zero_seq_hv: config.relay.filter_zero_seq_hv,
            filter_zero_seq_lv: config.relay.filter_zero_seq_lv,
          }),
        }),
      ]);

      await Promise.all([fetchConfig(), fetchPorts()]);
      flash("บันทึกการตั้งค่าทั้งหมดแล้ว");
    } catch {
      alert("บันทึกการตั้งค่าไม่สำเร็จ");
    } finally {
      setSavingAll(false);
    }
  };

  const commitInteger = async (
    draftKey: string,
    field: string,
    updateFn: (field: string, value: number) => Promise<void>,
    fallbackValue: number,
    minimum?: number
  ) => {
    const raw = drafts[draftKey] ?? "";
    if (raw.trim() === "") {
      setDraftValue(draftKey, String(fallbackValue));
      return;
    }
    const parsed = parseInt(raw, 10);
    if (Number.isNaN(parsed)) {
      setDraftValue(draftKey, String(fallbackValue));
      return;
    }
    const nextValue = minimum !== undefined ? Math.max(minimum, parsed) : parsed;
    setDraftValue(draftKey, String(nextValue));
    await updateFn(field, nextValue);
  };

  const commitFloat = async (
    draftKey: string,
    field: string,
    updateFn: (field: string, value: number) => Promise<void>,
    fallbackValue: number,
    minimum?: number,
    digits = 2
  ) => {
    const raw = drafts[draftKey] ?? "";
    if (raw.trim() === "") {
      setDraftValue(draftKey, fallbackValue.toFixed(digits));
      return;
    }
    const parsed = parseFloat(raw);
    if (Number.isNaN(parsed)) {
      setDraftValue(draftKey, fallbackValue.toFixed(digits));
      return;
    }
    const nextValue = minimum !== undefined ? Math.max(minimum, parsed) : parsed;
    setDraftValue(draftKey, nextValue.toFixed(digits));
    await updateFn(field, nextValue);
  };

  const handleEnterCommit =
    (commit: () => Promise<void>) => async (e: React.KeyboardEvent<HTMLInputElement>) => {
      if (e.key !== "Enter") return;
      e.currentTarget.blur();
      await commit();
    };

  return (
    <div className="p-4 space-y-4">
      {saved && (
        <div className="mb-3">
          <span className="text-[10px] text-green-400 bg-green-900/30 px-2 py-0.5 rounded animate-pulse">
            {saved}
          </span>
        </div>
      )}

      <div>
        <div className="card p-4 flex items-center justify-between gap-3">
          <div>
            <div className="text-sm font-semibold text-slate-200">Save Settings</div>
            <div className="text-xs text-slate-400 mt-1">
              หลังกรอกหรือปรับค่าต่าง ๆ แล้ว กดปุ่มนี้เพื่อยืนยันการตั้งค่าทั้งหมดอีกครั้งให้ชัวร์
            </div>
          </div>
          <button
            onClick={saveAllSettings}
            disabled={!config || savingAll}
            className="btn btn-primary px-4 py-2 text-xs whitespace-nowrap"
          >
            {savingAll ? "กำลังบันทึก..." : "บันทึกการตั้งค่า"}
          </button>
        </div>

        <div className="card p-5">
          <h2 className="text-sm font-semibold text-slate-200 mb-4">Connection & Mode</h2>

          {mode === "real" && (
            <div className="mb-4 rounded-lg border border-amber-500/30 bg-amber-500/10 px-3 py-2.5 text-xs text-amber-200">
              ตอนอยู่โหมด REAL ระบบจะพยายามคุยกับมิเตอร์จริง ให้ตรวจพอร์ตและสายสื่อสารก่อนกด connect
            </div>
          )}

          <div className="flex gap-3 mb-4">
            <button
              onClick={() => switchMode("simulation")}
              className={`flex-1 py-3 rounded-lg text-sm font-semibold transition-all ${
                mode === "simulation"
                  ? "bg-purple-600 text-white"
                  : "bg-slate-800 text-slate-400 hover:bg-slate-700"
              }`}
            >
              Simulation
            </button>
            <button
              onClick={() => switchMode("real")}
              className={`flex-1 py-3 rounded-lg text-sm font-semibold transition-all ${
                mode === "real"
                  ? "bg-green-600 text-white"
                  : "bg-slate-800 text-slate-400 hover:bg-slate-700"
              }`}
            >
              Real Hardware
            </button>
          </div>

          {mode === "real" && (
            <div>
              <div className="text-[10px] uppercase tracking-wider text-slate-500 mb-2">COM Ports</div>
              <div className="mb-3 rounded-lg border border-cyan-500/20 bg-cyan-500/5 px-3 py-2 text-[11px] text-cyan-100">
                ระบบจะสแกนพอร์ต serial ที่ใช้งานจริงและตัดพอร์ต Bluetooth ออก จากนั้นจะลองจับคู่มิเตอร์ address <span className="font-mono">1</span> และ <span className="font-mono">2</span> ให้เองเมื่อกด Auto Pair
              </div>
              <div className="mb-3 rounded-lg border border-slate-700 bg-slate-900/40 px-3 py-2 text-[11px] text-slate-300">
                ถ้าคุณรู้พอร์ตอยู่แล้ว แนะนำให้เลือก HV/LV Port เอง แล้วใช้ปุ่ม Connect Configured Ports เป็นหลัก
              </div>

              {connectingState && (
                <div className="mb-3 rounded-lg border border-blue-500/20 bg-blue-500/5 px-3 py-2 text-[11px] text-blue-100">
                  <span className="inline-flex items-center gap-2">
                    <span className="loading-spinner" />
                    {connectingState === "auto" ? "กำลังจับคู่มิเตอร์อัตโนมัติ..." : "กำลังเชื่อมต่อพอร์ตที่ตั้งไว้..."}
                  </span>
                </div>
              )}

              {config && (
                <div className="space-y-4 mb-3">
                  <div className="grid grid-cols-1 gap-4">
                    <div>
                      <label className="text-[10px] text-slate-500">RS485 Port (Shared for Meter #1 &amp; #2)</label>
                      <select
                        value={drafts.port || "auto"}
                        onChange={(e) => setDraftValue("port", e.target.value)}
                        onBlur={() => updateModbus("port", drafts.port || "auto")}
                        className="w-full mt-1 bg-slate-800 border border-slate-700 rounded-lg px-3 py-2 text-sm text-slate-200"
                      >
                        <option value="auto">auto</option>
                        {ports.map((port) => (
                          <option key={port} value={port}>
                            {port}
                          </option>
                        ))}
                      </select>
                    </div>
                  </div>

                  <div className="grid grid-cols-4 gap-4">
                    <div>
                      <label className="text-[10px] text-slate-500">Baudrate</label>
                      <input
                        type="number"
                        value={drafts.baudrate ?? ""}
                        onChange={(e) => setDraftValue("baudrate", e.target.value)}
                        onBlur={() =>
                          commitInteger(
                            "baudrate",
                            "baudrate",
                            async (field, value) => updateModbus(field, value),
                            config.modbus.baudrate,
                            1
                          )
                        }
                        onKeyDown={handleEnterCommit(() =>
                          commitInteger(
                            "baudrate",
                            "baudrate",
                            async (field, value) => updateModbus(field, value),
                            config.modbus.baudrate,
                            1
                          )
                        )}
                        className="w-full mt-1 bg-slate-800 border border-slate-700 rounded-lg px-3 py-2 text-sm text-slate-200"
                      />
                    </div>
                    <div>
                      <label className="text-[10px] text-slate-500">Parity</label>
                      <select
                        value={drafts.parity || config.modbus.parity}
                        onChange={(e) => setDraftValue("parity", e.target.value)}
                        onBlur={() => updateModbus("parity", drafts.parity || config.modbus.parity)}
                        className="w-full mt-1 bg-slate-800 border border-slate-700 rounded-lg px-3 py-2 text-sm text-slate-200"
                      >
                        <option value="N">N</option>
                        <option value="E">E</option>
                        <option value="O">O</option>
                      </select>
                    </div>
                    <div className="rounded-lg border border-slate-700 bg-slate-800/50 px-3 py-2">
                      <div className="text-[10px] text-slate-500">Meter #1 Address</div>
                      <div className="mt-1 text-sm font-mono text-slate-200">1</div>
                    </div>
                    <div className="rounded-lg border border-slate-700 bg-slate-800/50 px-3 py-2">
                      <div className="text-[10px] text-slate-500">Meter #2 Address</div>
                      <div className="mt-1 text-sm font-mono text-slate-200">2</div>
                    </div>
                  </div>

                  <button
                    onClick={() => connectPorts(config.modbus.port)}
                    disabled={connectingState !== null}
                    className="btn btn-primary text-xs py-2 w-full"
                  >
                    {connectingState === "manual" ? "กำลังเชื่อมต่อ..." : "Connect Configured Ports"}
                  </button>
                </div>
              )}

              <div className="grid grid-cols-1 gap-2 mb-2">
                <button
                  onClick={autoPairMeters}
                  disabled={connectingState !== null}
                  className="btn btn-outline text-xs py-2"
                >
                  {connectingState === "auto" ? "กำลังจับคู่มิเตอร์..." : "Auto Pair Meters (Optional)"}
                </button>
              </div>

              {ports.length > 0 && (
                <div className="mb-2 text-[10px] text-slate-500">พอร์ตที่พบ: {ports.join(", ")}</div>
              )}

              <button onClick={fetchPorts} className="text-[10px] text-slate-500 hover:text-slate-300">
                Refresh Port List
              </button>
            </div>
          )}

          <div className="mt-3 bg-slate-800/50 rounded-lg px-3 py-2 text-xs text-slate-400">
            Mode: <span className={mode === "real" ? "text-green-400" : "text-purple-400"}>{mode}</span>
            {data?.port && (
              <>
                {" · "}Port: <span className="text-slate-300">{data.port}</span>
              </>
            )}
            {" · "}Phase: <span className="text-cyan-400">{data?.relay.system_phase || "IDLE"}</span>
          </div>
        </div>

        <div className="card p-5">
          <h2 className="text-sm font-semibold text-slate-200 mb-4">Transformer</h2>

          <div className="mb-4 rounded-xl border border-cyan-500/20 bg-cyan-500/5 p-4">
            <div className="flex items-center justify-between gap-3">
              <div>
                <div className="text-sm font-semibold text-cyan-300">Autotransformer Test Preset</div>
                <div className="text-xs text-slate-400 mt-1">
                  ใช้ preset นี้เพื่อเซ็ตค่าพื้นฐานสำหรับ rig ทดสอบแบบ autotransformer ได้เร็วขึ้น
                </div>
              </div>
              <button onClick={applyAutotransformerPreset} className="btn btn-outline text-xs py-2 px-3">
                Apply Preset
              </button>
            </div>
            {presetNotes.length > 0 && (
              <div className="mt-3 space-y-1">
                {presetNotes.map((note) => (
                  <div key={note} className="text-[11px] text-slate-300">- {note}</div>
                ))}
              </div>
            )}
          </div>

          <div className="grid grid-cols-2 gap-4">
            <div>
              <label className="text-[10px] text-slate-500 uppercase tracking-wider">Equipment Mode</label>
              <select
                value={config?.transformer.equipment_mode || "transformer"}
                onChange={(e) => updateTransformer("equipment_mode", e.target.value)}
                className="w-full mt-1 bg-slate-800 border border-slate-700 rounded-lg px-3 py-2.5 text-sm text-slate-200 focus:border-cyan-500 outline-none"
              >
                <option value="transformer">Transformer</option>
                <option value="autotransformer">Autotransformer</option>
              </select>
            </div>

            <div>
              <label className="text-[10px] text-slate-500 uppercase tracking-wider">Detection Mode</label>
              <select
                value={config?.transformer.detection_mode || "auto_family"}
                onChange={(e) => updateTransformer("detection_mode", e.target.value)}
                className="w-full mt-1 bg-slate-800 border border-slate-700 rounded-lg px-3 py-2.5 text-sm text-slate-200 focus:border-cyan-500 outline-none"
              >
                <option value="auto_family">Auto Family (DD/DY/YD/YY)</option>
                <option value="manual_confirmed">Manual Confirmed</option>
                <option value="shared_vref">Shared Vref</option>
                <option value="voltage_ratio">Voltage Ratio</option>
              </select>
            </div>

            <div>
              <label className="text-[10px] text-slate-500 uppercase tracking-wider">
                {config?.transformer.detection_mode === "manual_confirmed" ? "Compensation Group" : "Detected Family"}
              </label>
              {config?.transformer.detection_mode === "manual_confirmed" ? (
                <select
                  value={config?.transformer.vector_group || "Dd0"}
                  onChange={(e) => updateTransformer("vector_group", e.target.value)}
                  className="w-full mt-1 bg-slate-800 border border-slate-700 rounded-lg px-3 py-2.5 text-sm text-slate-200 focus:border-cyan-500 outline-none"
                >
                  {VECTOR_GROUP_OPTIONS.map((group) => (
                    <option key={group} value={group}>{group}</option>
                  ))}
                </select>
              ) : (
                <div className="w-full mt-1 bg-slate-800 border border-slate-700 rounded-lg px-3 py-2.5 text-sm text-cyan-300 font-semibold">
                  {data?.relay.vector_family || "Unknown"}
                </div>
              )}
              <div className="text-[10px] text-slate-500 mt-1">
                {config?.transformer.detection_mode === "manual_confirmed"
                  ? "ใช้เมื่อคุณต้องการล็อก compensation group เอง"
                  : "หน้า dashboard จะแสดงและใช้งานเฉพาะ family แบบ DD/DY/YD/YY โดยไม่ใช้ subtype ย่อยแบบ Dy1 หรือ Dy11"}
              </div>
            </div>

            <div>
              <label className="text-[10px] text-slate-500 uppercase tracking-wider">Tap Position ({config?.transformer.tap_position})</label>
              <input
                type="range"
                min={1}
                max={10}
                value={config?.transformer.tap_position || 1}
                onChange={(e) => updateTransformer("tap_position", parseInt(e.target.value))}
                className="w-full mt-3 accent-cyan-500"
              />
              <div className="text-[10px] text-slate-400 mt-1 font-mono">
                V_HV: {config?.transformer.v_hv}V {"->"} V_LV: {config?.transformer.v_lv}V
              </div>
            </div>
          </div>

          <div className="grid grid-cols-2 gap-4 mt-4">
            <div className="rounded-lg border border-slate-700 bg-slate-800/40 px-3 py-3">
              <div className="text-[10px] text-slate-500 uppercase tracking-wider">Current Comparison Basis</div>
              <div className="text-sm font-semibold text-slate-200 mt-1">Line Current จากมิเตอร์จริง</div>
              <div className="text-[10px] text-slate-400 mt-2">
                ระบบใช้กระแส line current ที่ PM2200 วัดได้จริงเป็นค่าหลัก และค่อย refer เทียบอีกฝั่งด้วย turn ratio
              </div>
            </div>
            <div className="rounded-lg border border-cyan-500/20 bg-cyan-500/5 px-3 py-3">
              <div className="text-[10px] text-cyan-300 uppercase tracking-wider">
                {config?.transformer.equipment_mode === "autotransformer" ? "Autotransformer Turn Ratio" : "Transformer Turn Ratio"}
              </div>
              <div className="text-sm font-semibold text-cyan-200 mt-1">
                {config?.transformer.equipment_mode === "autotransformer"
                  ? `${config?.transformer.autotransformer_turns_ratio?.toFixed?.(2) ?? "2.00"} : 1 (fixed)`
                  : "คำนวณจากแรงดัน line-line ที่วัดได้จริง"}
              </div>
              <div className="text-[10px] text-slate-400 mt-2">
                โหมด Autotransformer จะล็อก ratio = 2 ตลอด ส่วนโหมด Transformer จะใช้อัตราส่วนแรงดัน HV/LV ที่วัดได้เพื่อ refer current
              </div>
            </div>
          </div>

          {config?.transformer.detection_mode === "auto_family" ? (
            <div className="mt-4 rounded-lg border border-cyan-500/20 bg-cyan-500/5 px-3 py-2.5 text-xs text-cyan-200">
              Auto Family จะอ่านรูปแบบการต่อจากแรงดันที่วัดได้และใช้งานเฉพาะ DD/DY/YD/YY โดยไม่ใช้ clock/subtype ย่อย
            </div>
          ) : config?.transformer.detection_mode === "manual_confirmed" ? (
            <div className="mt-4 rounded-lg border border-slate-700 bg-slate-800/40 px-3 py-2.5 text-xs text-slate-400">
              โหมด Manual Confirmed จะคง compensation group ที่เลือกไว้จนกว่าคุณจะเปลี่ยนเอง
            </div>
          ) : (
            <div className="flex gap-2 mt-4">
              <button onClick={autoDetect} disabled={detecting} className="btn btn-outline text-xs py-2 flex-1">
                {detecting ? "กำลังตรวจจับ..." : "Detect Vector Group"}
              </button>
              <button onClick={reDetect} className="btn btn-outline text-xs py-2 flex-1">
                Re-detect Pipeline
              </button>
            </div>
          )}

        </div>

        <div className="card p-5">
          <h2 className="text-sm font-semibold text-slate-200 mb-4">Protection Settings</h2>

          <div className="mb-4 rounded-lg border border-cyan-500/20 bg-cyan-500/5 px-3 py-2.5 text-xs text-cyan-200">
            ตอนนี้ protection ใช้หลักการ Biased Percentage Differential (Fixed I_pickup + Slopes) โดยจะปรับ threshold ตามสภาวะโหลดจริง
          </div>

          <div className="grid grid-cols-3 gap-4">
            <div>
              <label className="text-[10px] text-slate-500">Minimum Differential Trip (A)</label>
              <input
                type="number"
                step="0.01"
                value={drafts.i_pickup_amp ?? ""}
                onChange={(e) => setDraftValue("i_pickup_amp", e.target.value)}
                onBlur={() =>
                  commitFloat(
                    "i_pickup_amp",
                    "i_pickup",
                    async (field, value) => updateRelay(field, value),
                    config?.relay.i_pickup ?? 0,
                    0,
                    2
                  )
                }
                onKeyDown={handleEnterCommit(() =>
                  commitFloat(
                    "i_pickup_amp",
                    "i_pickup",
                    async (field, value) => updateRelay(field, value),
                    config?.relay.i_pickup ?? 0,
                    0,
                    2
                  )
                )}
                className="w-full mt-1 bg-slate-800 border border-slate-700 rounded-lg px-3 py-2 text-sm text-slate-200"
              />
              <div className="text-[10px] text-slate-500 mt-1">
                ค่านี้คือกระแส differential ต่ำสุดที่อนุญาตให้ relay เริ่มพิจารณา Trip
              </div>
            </div>
            <div>
              <label className="text-[10px] text-slate-500">Inrush Block (ms)</label>
              <input
                type="number"
                step="100"
                min="0"
                value={drafts.inrush_block_ms ?? ""}
                onChange={(e) => setDraftValue("inrush_block_ms", e.target.value)}
                onBlur={() =>
                  commitInteger(
                    "inrush_block_ms",
                    "inrush_block_ms",
                    async (field, value) => updateRelay(field, value),
                    config?.relay.inrush_block_ms ?? 700,
                    0
                  )
                }
                onKeyDown={handleEnterCommit(() =>
                  commitInteger(
                    "inrush_block_ms",
                    "inrush_block_ms",
                    async (field, value) => updateRelay(field, value),
                    config?.relay.inrush_block_ms ?? 700,
                    0
                  )
                )}
                className="w-full mt-1 bg-slate-800 border border-slate-700 rounded-lg px-3 py-2 text-sm text-slate-200"
              />
              <div className="text-[10px] text-slate-500 mt-1">ช่วงเวลาที่จะยังไม่ยอมให้ Trip หลังแรงดันเพิ่งขึ้น เพื่อกัน inrush</div>
            </div>
            <div>
              <label className="text-[10px] text-slate-500">Reset Delay (ms)</label>
              <input
                type="number"
                step="100"
                value={drafts.reset_delay_ms ?? ""}
                onChange={(e) => setDraftValue("reset_delay_ms", e.target.value)}
                onBlur={() =>
                  commitInteger(
                    "reset_delay_ms",
                    "reset_delay_ms",
                    async (field, value) => updateRelay(field, value),
                    config?.relay.reset_delay_ms || 5000,
                    0
                  )
                }
                onKeyDown={handleEnterCommit(() =>
                  commitInteger(
                    "reset_delay_ms",
                    "reset_delay_ms",
                    async (field, value) => updateRelay(field, value),
                    config?.relay.reset_delay_ms || 5000,
                    0
                  )
                )}
                className="w-full mt-1 bg-slate-800 border border-slate-700 rounded-lg px-3 py-2 text-sm text-slate-200"
              />
              <div className="text-[10px] text-slate-500 mt-1">เวลารอก่อน auto reset เมื่อ fault หาย</div>
            </div>
          </div>

          <div className="grid grid-cols-3 gap-4 mt-4">
            <div>
              <label className="text-[10px] text-slate-500">Slope 1 (0.0 - 1.0)</label>
              <input
                type="number"
                step="0.01"
                value={drafts.slope1 ?? ""}
                onChange={(e) => setDraftValue("slope1", e.target.value)}
                onBlur={() =>
                  commitFloat(
                    "slope1",
                    "slope1",
                    async (field, value) => updateRelay(field, value),
                    config?.relay.slope1 ?? 0.25,
                    0,
                    2
                  )
                }
                className="w-full mt-1 bg-slate-800 border border-slate-700 rounded-lg px-3 py-2 text-sm text-slate-200"
              />
            </div>
            <div>
              <label className="text-[10px] text-slate-500">Slope 2 (0.0 - 1.0)</label>
              <input
                type="number"
                step="0.01"
                value={drafts.slope2 ?? ""}
                onChange={(e) => setDraftValue("slope2", e.target.value)}
                onBlur={() =>
                  commitFloat(
                    "slope2",
                    "slope2",
                    async (field, value) => updateRelay(field, value),
                    config?.relay.slope2 ?? 0.50,
                    0,
                    2
                  )
                }
                className="w-full mt-1 bg-slate-800 border border-slate-700 rounded-lg px-3 py-2 text-sm text-slate-200"
              />
            </div>
            <div>
              <label className="text-[10px] text-slate-500">Bias Breakpoint (PU)</label>
              <input
                type="number"
                step="0.1"
                value={drafts.bias_breakpoint ?? ""}
                onChange={(e) => setDraftValue("bias_breakpoint", e.target.value)}
                onBlur={() =>
                  commitFloat(
                    "bias_breakpoint",
                    "bias_breakpoint",
                    async (field, value) => updateRelay(field, value),
                    config?.relay.bias_breakpoint ?? 1.0,
                    0,
                    2
                  )
                }
                className="w-full mt-1 bg-slate-800 border border-slate-700 rounded-lg px-3 py-2 text-sm text-slate-200"
              />
            </div>
          </div>

          <div className="mt-4 rounded-lg border border-slate-700 bg-slate-800/40 px-3 py-2.5 text-xs text-slate-400">
            ระบบคำนวณ Threshold แบบ Dynamic จากสมการ: Trip = i_diff {">"} (i_pickup + Slope * i_bias) เพื่อป้องกัน False Trip ในสภาวะโหลดสูง
          </div>

          <div className="mt-4 space-y-2">
            <label className="flex items-center gap-2 cursor-pointer">
              <input
                type="checkbox"
                checked={config?.relay.trip_enabled ?? true}
                onChange={(e) => updateRelay("trip_enabled", e.target.checked)}
                className="accent-cyan-500"
              />
              <span className="text-xs text-slate-400">เปิดการทำงานของ Trip (ถ้าปิด ระบบจะคำนวณอย่างเดียว)</span>
            </label>
            <label className="flex items-center gap-2 cursor-pointer">
              <input
                type="checkbox"
                checked={config?.relay.auto_reset ?? true}
                onChange={(e) => updateRelay("auto_reset", e.target.checked)}
                className="accent-cyan-500"
              />
              <span className="text-xs text-slate-400">Auto Reset (เคลียร์ Trip อัตโนมัติเมื่อ fault หาย)</span>
            </label>
            <label className="flex items-center gap-2 cursor-pointer">
              <input
                type="checkbox"
                checked={config?.relay.filter_zero_seq_hv ?? false}
                onChange={(e) => updateRelay("filter_zero_seq_hv", e.target.checked)}
                className="accent-cyan-500"
              />
              <span className="text-xs text-slate-400">กรอง Zero-Seq (HV)</span>
            </label>
            <label className="flex items-center gap-2 cursor-pointer">
              <input
                type="checkbox"
                checked={config?.relay.filter_zero_seq_lv ?? false}
                onChange={(e) => updateRelay("filter_zero_seq_lv", e.target.checked)}
                className="accent-cyan-500"
              />
              <span className="text-xs text-slate-400">กรอง Zero-Seq (LV)</span>
            </label>
          </div>
        </div>

        {data?.relay.detection && (
          <div className="card p-5">
            <h2 className="text-sm font-semibold text-slate-200 mb-3">Detection Details</h2>
            <pre className="text-[10px] text-slate-400 bg-slate-800/50 rounded-lg p-3 overflow-x-auto">
              {JSON.stringify(data.relay.detection, null, 2)}
            </pre>
          </div>
        )}
      </div>
    </div>
  );
}

export default function SettingsPage() {
  return <SettingsContent />;
}
