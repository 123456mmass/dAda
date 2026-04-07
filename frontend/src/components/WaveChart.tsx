"use client";

import React, { useMemo } from "react";
import {
  LineChart,
  Line,
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip,
  ResponsiveContainer,
  Legend,
} from "recharts";
import { WaveformData } from "@/context/AppContext";

interface WaveChartProps {
  waveforms: WaveformData | undefined;
}

export default function WaveChart({ waveforms }: WaveChartProps) {
  // Build chart data arrays from waveform data
  const { hvVoltData, lvVoltData, hvCurrData, lvCurrData, hvNeutData, lvNeutData } =
    useMemo(() => {
      if (!waveforms) return {
        hvVoltData: [], lvVoltData: [],
        hvCurrData: [], lvCurrData: [],
        hvNeutData: [], lvNeutData: []
      };

      const time = waveforms.time_ms;
      const hv = waveforms.hv;
      const lv = waveforms.lv;

      const hvVolt = time.map((t, i) => ({
        time: t,
        ab: hv.voltage_ll.ab[i],
        bc: hv.voltage_ll.bc[i],
        ca: hv.voltage_ll.ca[i],
      }));

      const lvVolt = time.map((t, i) => ({
        time: t,
        ab: lv.voltage_ll.ab[i],
        bc: lv.voltage_ll.bc[i],
        ca: lv.voltage_ll.ca[i],
      }));

      const hvCurr = time.map((t, i) => ({
        time: t,
        a: hv.current_l.a[i],
        b: hv.current_l.b[i],
        c: hv.current_l.c[i],
      }));

      const lvCurr = time.map((t, i) => ({
        time: t,
        a: lv.current_l.a[i],
        b: lv.current_l.b[i],
        c: lv.current_l.c[i],
      }));

      const hvNeut = time.map((t, i) => ({
        time: t,
        n: hv.current_n[i],
      }));

      const lvNeut = time.map((t, i) => ({
        time: t,
        n: lv.current_n[i],
      }));

      return { hvVoltData: hvVolt, lvVoltData: lvVolt, hvCurrData: hvCurr, lvCurrData: lvCurr, hvNeutData: hvNeut, lvNeutData: lvNeut };
    }, [waveforms]);

  if (!waveforms) {
    return (
      <div className="card flex h-[400px] items-center justify-center text-slate-500">
        ยังไม่มีข้อมูล waveform
      </div>
    );
  }

  return (
    <div className="space-y-6">
      <div className="grid grid-cols-1 gap-6 lg:grid-cols-2">
        {/* HV Voltage */}
        <div className="card p-4">
          <h3 className="mb-4 text-sm font-semibold text-slate-300">HV Voltage (L-L)</h3>
          <div className="h-[250px]">
            <ResponsiveContainer width="100%" height="100%">
              <LineChart data={hvVoltData}>
                <CartesianGrid strokeDasharray="3 3" stroke="rgba(255,255,255,0.05)" />
                <XAxis dataKey="time" hide />
                <YAxis fontSize={10} unit="V" />
                <Tooltip
                  contentStyle={{ backgroundColor: "#1e293b", border: "none", fontSize: "10px" }}
                />
                <Legend iconType="circle" />
                <Line type="monotone" dataKey="ab" name="Vab" stroke="#ef4444" dot={false} strokeWidth={2} isAnimationActive={false} />
                <Line type="monotone" dataKey="bc" name="Vbc" stroke="#fb923c" dot={false} strokeWidth={2} isAnimationActive={false} />
                <Line type="monotone" dataKey="ca" name="Vca" stroke="#3b82f6" dot={false} strokeWidth={2} isAnimationActive={false} />
              </LineChart>
            </ResponsiveContainer>
          </div>
        </div>

        {/* LV Voltage */}
        <div className="card p-4">
          <h3 className="mb-4 text-sm font-semibold text-slate-300">LV Voltage (L-L)</h3>
          <div className="h-[250px]">
            <ResponsiveContainer width="100%" height="100%">
              <LineChart data={lvVoltData}>
                <CartesianGrid strokeDasharray="3 3" stroke="rgba(255,255,255,0.05)" />
                <XAxis dataKey="time" hide />
                <YAxis fontSize={10} unit="V" />
                <Tooltip
                  contentStyle={{ backgroundColor: "#1e293b", border: "none", fontSize: "10px" }}
                />
                <Legend iconType="circle" />
                <Line type="monotone" dataKey="ab" name="Vab" stroke="#ef4444" dot={false} strokeWidth={2} isAnimationActive={false} />
                <Line type="monotone" dataKey="bc" name="Vbc" stroke="#fb923c" dot={false} strokeWidth={2} isAnimationActive={false} />
                <Line type="monotone" dataKey="ca" name="Vca" stroke="#3b82f6" dot={false} strokeWidth={2} isAnimationActive={false} />
              </LineChart>
            </ResponsiveContainer>
          </div>
        </div>

        {/* HV Current */}
        <div className="card p-4">
          <h3 className="mb-4 text-sm font-semibold text-slate-300">HV Current</h3>
          <div className="h-[250px]">
            <ResponsiveContainer width="100%" height="100%">
              <LineChart data={hvCurrData}>
                <CartesianGrid strokeDasharray="3 3" stroke="rgba(255,255,255,0.05)" />
                <XAxis dataKey="time" hide />
                <YAxis fontSize={10} unit="A" />
                <Tooltip
                  contentStyle={{ backgroundColor: "#1e293b", border: "none", fontSize: "10px" }}
                />
                <Legend iconType="circle" />
                <Line type="monotone" dataKey="a" name="Ia" stroke="#ef4444" dot={false} strokeWidth={2} isAnimationActive={false} />
                <Line type="monotone" dataKey="b" name="Ib" stroke="#fb923c" dot={false} strokeWidth={2} isAnimationActive={false} />
                <Line type="monotone" dataKey="c" name="Ic" stroke="#3b82f6" dot={false} strokeWidth={2} isAnimationActive={false} />
              </LineChart>
            </ResponsiveContainer>
          </div>
        </div>

        {/* LV Current */}
        <div className="card p-4">
          <h3 className="mb-4 text-sm font-semibold text-slate-300">LV Current</h3>
          <div className="h-[250px]">
            <ResponsiveContainer width="100%" height="100%">
              <LineChart data={lvCurrData}>
                <CartesianGrid strokeDasharray="3 3" stroke="rgba(255,255,255,0.05)" />
                <XAxis dataKey="time" hide />
                <YAxis fontSize={10} unit="A" />
                <Tooltip
                  contentStyle={{ backgroundColor: "#1e293b", border: "none", fontSize: "10px" }}
                />
                <Legend iconType="circle" />
                <Line type="monotone" dataKey="a" name="Ia" stroke="#ef4444" dot={false} strokeWidth={2} isAnimationActive={false} />
                <Line type="monotone" dataKey="b" name="Ib" stroke="#fb923c" dot={false} strokeWidth={2} isAnimationActive={false} />
                <Line type="monotone" dataKey="c" name="Ic" stroke="#3b82f6" dot={false} strokeWidth={2} isAnimationActive={false} />
              </LineChart>
            </ResponsiveContainer>
          </div>
        </div>
      </div>
    </div>
  );
}
