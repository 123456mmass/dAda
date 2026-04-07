"use client";

import React, { useEffect, useState } from "react";
import { RelayData } from "@/context/AppContext";

interface Props {
  relay: RelayData;
  muted: boolean;
  onToggleMute: () => void;
  onDismiss: () => void;
}

export default function TripAlert({
  relay,
  muted,
  onToggleMute,
  onDismiss,
}: Props) {
  const [show, setShow] = useState(false);

  useEffect(() => {
    setShow(true);
    // Play sound if not muted
    if (!muted) {
      const audio = new Audio("/trip-alarm.mp3");
      audio.loop = true;
      audio.play().catch(() => console.log("Audio play failed"));
      return () => {
        audio.pause();
        audio.src = "";
      };
    }
  }, [muted]);

  return (
    <div
      className={`fixed inset-0 z-[100] flex items-center justify-center bg-red-950/80 p-4 transition-opacity duration-500 ${
        show ? "opacity-100" : "opacity-0"
      }`}
    >
      <div className="w-full max-w-md animate-bounce rounded-2xl border-2 border-red-500 bg-slate-900 p-8 text-center shadow-[0_0_50px_rgba(239,68,68,0.5)]">
        <div className="mb-4 text-6xl text-red-500">⚠</div>
        <h2 className="mb-2 text-3xl font-black tracking-tighter text-white">
          DIFFERENTIAL TRIP
        </h2>
        <div className="mb-6 space-y-2">
          <p className="text-red-400">
            ระบบตรวจพบความต่างของกระแสเกินขีดจำกัด
          </p>
          <div className="flex justify-center gap-3 text-sm font-mono text-slate-400">
            {relay.last_trip_phases.map((ph) => (
              <span key={ph} className="rounded bg-red-900/30 px-2 py-1 text-red-300">
                Phase {ph}
              </span>
            ))}
          </div>
        </div>

        <div className="flex flex-col gap-3">
          <button
            onClick={onToggleMute}
            className="w-full rounded-xl bg-slate-800 py-3 font-bold text-white transition-colors hover:bg-slate-700"
          >
            {muted ? "🔈 Unmute Alarm" : "🔇 Mute Alarm"}
          </button>
          <button
            onClick={onDismiss}
            className="w-full rounded-xl bg-red-600 py-3 font-bold text-white transition-colors hover:bg-red-500"
          >
            Acknowledge & Dismiss
          </button>
        </div>
      </div>
    </div>
  );
}
